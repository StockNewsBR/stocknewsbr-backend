import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.cache import paper_trading_cache as paper_cache_module
from app.cache.paper_trading_cache import PaperTradingCache
from app.system.paper_trading import update_paper_trading_from_snapshot


def _row(
    decision="BUY",
    *,
    symbol="PETR4",
    price=100.0,
    volume=1_000_000,
    data_quality="real_time",
    decision_ready=True,
):
    return {
        "ticker": symbol,
        "symbol": symbol,
        "signal": decision,
        "trade_action": decision,
        "decision_ready": decision_ready,
        "data_quality": data_quality,
        "price": price,
        "volume": volume,
        "audit_status": "APPROVED",
        "auditor_status": "APPROVED",
        "blocked_by_auditor": False,
        "operational_status": "READY",
        "final_decision": "OPORTUNIDADE CONFIRMADA",
        "final_decision_blocks": [],
        "final_decision_confidence": 82.0,
        "conviction_level": "ALTA",
    }


def _snapshot(rows, *, stale=False, generated_at=2_000_000_000.0):
    return {
        "signals": rows,
        "source": "engine",
        "stale": stale,
        "generated_at": generated_at,
        "go_live_ready": True,
        "institutional_certified": True,
        "institutional_consistency_score": 100.0,
        "contract_coverage": {"total": len(rows), "complete": len(rows), "missing": 0, "coverage_pct": 100.0},
    }


def _position(symbol, side, *, price=100.0, opened_at=10.0):
    return {
        "mode": "PAPER_ONLY",
        "simulation": "SIMULATED",
        "position_id": f"{symbol}:{side}:{int(opened_at * 1000)}",
        "symbol": symbol,
        "side": side,
        "entry_price": price,
        "entry_timestamp": opened_at,
        "entry_decision": "BUY" if side == "LONG" else "SHORT",
        "entry_final_decision": "OPORTUNIDADE CONFIRMADA",
        "confidence": 82.0,
        "conviction": "ALTA",
        "source_snapshot_timestamp": opened_at,
        "status": "OPEN",
    }


class Mission31GInstitutionalIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.state_path = Path(self.tmp.name) / "paper_trading.json"
        self.original_cache = paper_cache_module.paper_trading_cache
        paper_cache_module.paper_trading_cache = PaperTradingCache(self.state_path)

    def tearDown(self):
        paper_cache_module.paper_trading_cache = self.original_cache
        self.tmp.cleanup()

    def _seed_positions(self, *positions):
        state = paper_cache_module.paper_trading_cache.get()
        state["positions"] = [dict(position) for position in positions]
        paper_cache_module.paper_trading_cache.update(state)

    def _assert_single_skip(self, state, *, symbol, decision, reason):
        self.assertEqual(state["metrics"]["skipped_signals"], 1)
        self.assertEqual(state["metrics"]["skipped_reasons"], {reason: 1})
        self.assertEqual(len(state["skipped"]), 1)
        skip = state["skipped"][0]
        self.assertEqual(skip["mode"], "PAPER_ONLY")
        self.assertEqual(skip["simulation"], "SIMULATED")
        self.assertEqual(skip["symbol"], symbol)
        self.assertEqual(skip["decision"], decision)
        self.assertEqual(skip["skipped_reason"], reason)
        self.assertIn("timestamp", skip)
        self.assertIn("source_snapshot_timestamp", skip)

    def _assert_closed_trade(self, state, *, side, decision, return_pct):
        self.assertEqual(state["metrics"]["closed_trades"], 1)
        self.assertEqual(len(state["trades"]), 1)
        trade = state["trades"][0]
        self.assertEqual(trade["mode"], "PAPER_ONLY")
        self.assertEqual(trade["simulation"], "SIMULATED")
        self.assertEqual(trade["symbol"], "PETR4")
        self.assertEqual(trade["side"], side)
        self.assertEqual(trade["exit_decision"], decision)
        self.assertEqual(trade["return_pct"], return_pct)

    def test_exit_and_close_close_short_when_only_short_is_open(self):
        for decision in ("EXIT", "CLOSE"):
            with self.subTest(decision=decision):
                paper_cache_module.paper_trading_cache.reset()
                update_paper_trading_from_snapshot(_snapshot([_row("SHORT", price=100.0)]), now=10.0)

                state = update_paper_trading_from_snapshot(_snapshot([_row(decision, price=90.0)]), now=20.0)

                self.assertEqual(state["metrics"]["open_trades"], 0)
                self.assertEqual(state["metrics"]["skipped_signals"], 0)
                self.assertEqual(state["metrics"]["skipped_reasons"], {})
                self._assert_closed_trade(state, side="SHORT", decision=decision, return_pct=10.0)

    def test_exit_and_close_continue_to_close_long_when_only_long_is_open(self):
        for decision in ("EXIT", "CLOSE"):
            with self.subTest(decision=decision):
                paper_cache_module.paper_trading_cache.reset()
                update_paper_trading_from_snapshot(_snapshot([_row("BUY", price=100.0)]), now=10.0)

                state = update_paper_trading_from_snapshot(_snapshot([_row(decision, price=110.0)]), now=20.0)

                self.assertEqual(state["metrics"]["open_trades"], 0)
                self.assertEqual(state["metrics"]["skipped_signals"], 0)
                self.assertEqual(state["metrics"]["skipped_reasons"], {})
                self._assert_closed_trade(state, side="LONG", decision=decision, return_pct=10.0)

    def test_exit_and_close_prefer_long_when_same_symbol_long_and_short_are_open(self):
        for decision in ("EXIT", "CLOSE"):
            with self.subTest(decision=decision):
                paper_cache_module.paper_trading_cache.reset()
                self._seed_positions(
                    _position("PETR4", "LONG", price=100.0),
                    _position("PETR4", "SHORT", price=100.0),
                )

                state = update_paper_trading_from_snapshot(_snapshot([_row(decision, price=110.0)]), now=20.0)

                self.assertEqual(state["metrics"]["open_trades"], 1)
                self.assertEqual(state["metrics"]["closed_trades"], 1)
                self.assertEqual(state["metrics"]["skipped_signals"], 0)
                self.assertEqual(state["metrics"]["skipped_reasons"], {})
                self._assert_closed_trade(state, side="LONG", decision=decision, return_pct=10.0)
                open_positions = [position for position in state["positions"] if position["status"] == "OPEN"]
                self.assertEqual(len(open_positions), 1)
                self.assertEqual(open_positions[0]["symbol"], "PETR4")
                self.assertEqual(open_positions[0]["side"], "SHORT")

    def test_sell_does_not_close_short_indirectly(self):
        update_paper_trading_from_snapshot(_snapshot([_row("SHORT", price=100.0)]), now=10.0)

        state = update_paper_trading_from_snapshot(_snapshot([_row("SELL", price=90.0)]), now=20.0)

        self.assertEqual(state["metrics"]["open_trades"], 1)
        self.assertEqual(state["metrics"]["closed_trades"], 0)
        self._assert_single_skip(state, symbol="PETR4", decision="SELL", reason="no_open_long_position")
        self.assertEqual(state["positions"][0]["side"], "SHORT")
        self.assertEqual(state["positions"][0]["status"], "OPEN")

    def test_cover_does_not_close_long_indirectly(self):
        update_paper_trading_from_snapshot(_snapshot([_row("BUY", price=100.0)]), now=10.0)

        state = update_paper_trading_from_snapshot(_snapshot([_row("COVER", price=110.0)]), now=20.0)

        self.assertEqual(state["metrics"]["open_trades"], 1)
        self.assertEqual(state["metrics"]["closed_trades"], 0)
        self._assert_single_skip(state, symbol="PETR4", decision="COVER", reason="no_open_short_position")
        self.assertEqual(state["positions"][0]["side"], "LONG")
        self.assertEqual(state["positions"][0]["status"], "OPEN")

    def test_exit_and_close_without_open_position_use_specific_skip_bucket(self):
        for decision in ("EXIT", "CLOSE"):
            with self.subTest(decision=decision):
                paper_cache_module.paper_trading_cache.reset()

                state = update_paper_trading_from_snapshot(_snapshot([_row(decision, symbol="PETR4")]), now=20.0)

                self.assertEqual(state["metrics"]["open_trades"], 0)
                self.assertEqual(state["metrics"]["closed_trades"], 0)
                self._assert_single_skip(state, symbol="PETR4", decision=decision, reason="no_open_position")

    def test_cross_symbol_exit_keeps_open_position_and_records_specific_skip_bucket(self):
        update_paper_trading_from_snapshot(_snapshot([_row("BUY", symbol="PETR4", price=100.0)]), now=10.0)

        state = update_paper_trading_from_snapshot(_snapshot([_row("EXIT", symbol="VALE3", price=110.0)]), now=20.0)

        self.assertEqual(state["metrics"]["open_trades"], 1)
        self.assertEqual(state["metrics"]["closed_trades"], 0)
        self._assert_single_skip(state, symbol="VALE3", decision="EXIT", reason="no_open_position")
        self.assertEqual(state["positions"][0]["symbol"], "PETR4")
        self.assertEqual(state["positions"][0]["side"], "LONG")
        self.assertEqual(state["positions"][0]["status"], "OPEN")

    def test_close_guards_still_block_stale_or_invalid_data_before_position_close(self):
        update_paper_trading_from_snapshot(_snapshot([_row("SHORT", price=100.0)]), now=10.0)

        state = update_paper_trading_from_snapshot(_snapshot([_row("CLOSE", price=90.0)], stale=True), now=20.0)

        self.assertEqual(state["metrics"]["open_trades"], 1)
        self.assertEqual(state["metrics"]["closed_trades"], 0)
        self._assert_single_skip(state, symbol="PETR4", decision="CLOSE", reason="snapshot_stale")
        self.assertEqual(state["positions"][0]["side"], "SHORT")
        self.assertEqual(state["positions"][0]["status"], "OPEN")

    def test_exit_and_close_tests_do_not_call_external_provider(self):
        with patch("app.market.market_data_loader._get_yfinance", side_effect=AssertionError("provider must not be called")):
            state = update_paper_trading_from_snapshot(_snapshot([_row("EXIT", symbol="PETR4")]), now=20.0)

        self._assert_single_skip(state, symbol="PETR4", decision="EXIT", reason="no_open_position")


if __name__ == "__main__":
    unittest.main()
