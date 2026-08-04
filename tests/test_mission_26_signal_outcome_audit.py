import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.system.signal_outcome_audit as signal_outcome_audit_module
from app.api import routes_paper_trading
from app.cache import paper_trading_cache as paper_cache_module
from app.cache import signal_outcome_cache as outcome_cache_module
from app.cache.paper_trading_cache import PaperTradingCache
from app.cache.signal_outcome_cache import SignalOutcomeCache
from app.dependencies import require_internal_token
from app.system.paper_trading import update_paper_trading_from_snapshot
from app.system.signal_outcome_audit import get_signal_outcome_audit_status, update_signal_outcome_audit_from_snapshot


def _row(
    decision="BUY",
    *,
    symbol="PETR4",
    price=100.0,
    volume=1_000_000,
    data_quality="real_time",
    decision_ready=True,
    audit_status="APPROVED",
    master_score=82.0,
    regime="trend",
):
    row = {
        "ticker": symbol,
        "symbol": symbol,
        "signal": decision,
        "trade_action": decision,
        "decision_ready": decision_ready,
        "decision_state": "BUY_READY" if decision == "BUY" else "SHORT_READY" if decision == "SHORT" else "",
        "data_quality": data_quality,
        "price": price,
        "volume": volume,
        "audit_status": audit_status,
        "auditor_status": audit_status,
        "blocked_by_auditor": audit_status == "BLOCKED",
        "operational_status": "READY" if decision_ready else "BLOCKED",
        "final_decision": "OPORTUNIDADE CONFIRMADA" if decision_ready else "NÃO OPERAR AGORA",
        "final_decision_blocks": [] if decision_ready else ["decision not ready"],
        "final_decision_confidence": 82.0,
        "conviction_level": "ALTA",
        "priority_level": "ALTA",
        "master_score": master_score,
        "master_score_raw": master_score,
        "master_score_source_scale": "0_100",
        "ranking_opportunity_score": master_score,
        "ranking_opportunity_source_scale": "0_100",
        "master_status": "APPROVED" if audit_status != "BLOCKED" else "BLOCKED",
        "master_direction": "BULLISH" if decision in {"BUY", "COVER", "WAIT"} else "BEARISH",
        "historical_confidence_score": 72.0,
        "market_regime": regime,
    }
    row["score_source_scale"] = "0_100"
    return row


def _snapshot(rows, *, generated_at=1_000.0, stale=False, market_closed=False):
    return {
        "signals": rows,
        "source": "engine",
        "stale": stale,
        "generated_at": generated_at,
        "market_closed": market_closed,
        "go_live_ready": True,
        "institutional_certified": True,
        "institutional_consistency_score": 100.0,
        "contract_coverage": {"total": len(rows), "complete": len(rows), "missing": 0, "coverage_pct": 100.0},
    }


class Mission26SignalOutcomeAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.paper_state_path = Path(self.tmp.name) / "paper_trading.json"
        self.outcome_state_path = Path(self.tmp.name) / "signal_outcomes.json"
        self.original_paper_cache = paper_cache_module.paper_trading_cache
        self.original_outcome_cache = outcome_cache_module.signal_outcome_cache
        paper_cache_module.paper_trading_cache = PaperTradingCache(self.paper_state_path)
        outcome_cache_module.signal_outcome_cache = SignalOutcomeCache(self.outcome_state_path)

    def tearDown(self):
        paper_cache_module.paper_trading_cache = self.original_paper_cache
        outcome_cache_module.signal_outcome_cache = self.original_outcome_cache
        self.tmp.cleanup()

    def test_blocked_signal_never_becomes_paper_trade_but_outcome_is_audited(self):
        entry = _row("BUY", symbol="BLOCK1", audit_status="BLOCKED")
        future = _row("BUY", symbol="BLOCK1", price=110.0, audit_status="BLOCKED")

        paper_state = update_paper_trading_from_snapshot(_snapshot([entry], generated_at=1_000.0), now=1_000.0)
        update_signal_outcome_audit_from_snapshot(_snapshot([entry], generated_at=1_000.0), now=1_000.0)
        state = update_signal_outcome_audit_from_snapshot(_snapshot([future], generated_at=1_300.0), now=1_300.0)

        self.assertEqual(paper_state["metrics"]["open_trades"], 0)
        self.assertEqual(state["records"][0]["status"], "blocked")
        self.assertEqual(state["records"][0]["simulated_result"], "winner")
        self.assertFalse(state["records"][0]["paper_trade_executed"])
        self.assertEqual(state["metrics"]["blocked_would_have_won"], 1)

    def test_blocked_signal_never_counts_as_loss(self):
        entry = _row("BUY", symbol="BLOCKLOSS", audit_status="BLOCKED")
        future = _row("BUY", symbol="BLOCKLOSS", price=90.0, audit_status="BLOCKED")

        update_signal_outcome_audit_from_snapshot(_snapshot([entry], generated_at=1_000.0), now=1_000.0)
        state = update_signal_outcome_audit_from_snapshot(_snapshot([future], generated_at=1_300.0), now=1_300.0)

        self.assertEqual(state["records"][0]["status"], "blocked")
        self.assertEqual(state["records"][0]["simulated_result"], "loser")
        self.assertEqual(state["metrics"]["loser_signals"], 0)
        self.assertEqual(state["metrics"]["false_positive_rate"], 0.0)

    def test_signal_without_future_data_is_insufficient_data(self):
        state = update_signal_outcome_audit_from_snapshot(_snapshot([_row("BUY")], generated_at=1_000.0), now=1_000.0)

        self.assertEqual(state["records"][0]["status"], "insufficient_data")
        self.assertEqual(state["records"][0]["simulated_result"], "insufficient_data")
        self.assertEqual(state["metrics"]["insufficient_data"], 1)
        self.assertEqual(state["metrics"]["win_rate"], 0.0)

    def test_stale_future_data_does_not_fill_outcome_window(self):
        update_signal_outcome_audit_from_snapshot(_snapshot([_row("BUY", symbol="STALE1")], generated_at=1_000.0), now=1_000.0)
        state = update_signal_outcome_audit_from_snapshot(
            _snapshot([_row("BUY", symbol="STALE1", price=120.0)], generated_at=1_300.0, stale=True),
            now=1_300.0,
        )

        original = next(record for record in state["records"] if record["ticker"] == "STALE1" and record["actionability"] is True)
        self.assertEqual(original["windows"]["5m"]["status"], "pending")
        self.assertEqual(original["simulated_result"], "insufficient_data")

    def test_skipped_signal_is_not_counted_as_loss(self):
        update_signal_outcome_audit_from_snapshot(_snapshot([_row("WAIT", symbol="WAIT1")], generated_at=1_000.0), now=1_000.0)
        state = update_signal_outcome_audit_from_snapshot(_snapshot([_row("WAIT", symbol="WAIT1", price=80.0)], generated_at=1_300.0), now=1_300.0)

        self.assertEqual(state["records"][0]["status"], "skipped")
        self.assertEqual(state["metrics"]["skipped_signals"], 1)
        self.assertEqual(state["metrics"]["loser_signals"], 0)
        self.assertEqual(state["metrics"]["false_positive_rate"], 0.0)

    def test_win_rate_only_counts_executable_simulated_signals(self):
        entry_rows = [
            _row("BUY", symbol="WIN1", price=100.0),
            _row("BUY", symbol="BLOCK2", price=100.0, audit_status="BLOCKED"),
        ]
        future_rows = [
            _row("BUY", symbol="WIN1", price=110.0),
            _row("BUY", symbol="BLOCK2", price=110.0, audit_status="BLOCKED"),
        ]

        update_signal_outcome_audit_from_snapshot(_snapshot(entry_rows, generated_at=1_000.0), now=1_000.0)
        state = update_signal_outcome_audit_from_snapshot(_snapshot(future_rows, generated_at=1_300.0), now=1_300.0)

        self.assertEqual(state["metrics"]["evaluated_executable_signals"], 1)
        self.assertEqual(state["metrics"]["winner_signals"], 1)
        self.assertEqual(state["metrics"]["win_rate"], 100.0)
        self.assertEqual(state["metrics"]["false_negative_rate"], 100.0)

    def test_mfe_mae_and_windows_are_calculated_from_real_future_snapshots(self):
        update_signal_outcome_audit_from_snapshot(_snapshot([_row("BUY", symbol="PETR4", price=100.0)], generated_at=1_000.0), now=1_000.0)
        update_signal_outcome_audit_from_snapshot(_snapshot([_row("BUY", symbol="PETR4", price=105.0)], generated_at=1_300.0), now=1_300.0)
        state = update_signal_outcome_audit_from_snapshot(_snapshot([_row("BUY", symbol="PETR4", price=95.0)], generated_at=1_899.0), now=1_899.0)

        record = state["records"][0]
        self.assertEqual(record["windows"]["5m"]["status"], "filled")
        self.assertEqual(record["windows"]["15m"]["status"], "pending")
        self.assertEqual(record["mfe_pct"], 5.0)
        self.assertEqual(record["mae_pct"], -5.0)
        self.assertEqual(state["metrics"]["average_mfe_pct"], 5.0)
        self.assertEqual(state["metrics"]["average_mae_pct"], -5.0)

    def test_internal_endpoint_exposes_paper_only_outcome_audit(self):
        update_signal_outcome_audit_from_snapshot(_snapshot([_row("BUY")], generated_at=1_000.0), now=1_000.0)
        app = FastAPI()
        app.include_router(routes_paper_trading.router)
        app.dependency_overrides[require_internal_token] = lambda: True

        response = TestClient(app).get("/internal/paper-trading/outcomes")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["paper_only"])
        self.assertEqual(payload["mode"], "PAPER_ONLY")
        self.assertEqual(payload["simulation"], "SIMULATED")
        self.assertIn("win_rate", payload["metrics"])

    def test_paper_trading_mode_remains_paper_only_simulated(self):
        update_paper_trading_from_snapshot(_snapshot([_row("BUY")], generated_at=1_000.0), now=1_000.0)
        state = get_signal_outcome_audit_status()

        self.assertEqual(state["mode"], "PAPER_ONLY")
        self.assertEqual(state["simulation"], "SIMULATED")

    def test_outcome_audit_does_not_call_external_provider(self):
        source = Path(signal_outcome_audit_module.__file__).read_text(encoding="utf-8")
        for forbidden in ("yfinance", "requests.", "httpx", "urlopen", "urllib", "download(", "fetch("):
            self.assertNotIn(forbidden, source)

        with patch("app.market.market_data_loader._get_yfinance", side_effect=AssertionError("provider must not be called")):
            state = update_signal_outcome_audit_from_snapshot(_snapshot([_row("BUY")], generated_at=1_000.0), now=1_000.0)

        self.assertEqual(state["records"][0]["ticker"], "PETR4")

    def test_worker_loop_calls_outcome_audit_without_crashing(self):
        import worker

        class StopAfterFirst:
            def is_set(self):
                return False

            def wait(self, seconds):
                return True

        snapshot = _snapshot([_row("BUY", symbol="WORK1")], generated_at=1_000.0)
        snapshot["snapshot_runtime_status"] = "HEALTHY"

        with patch.object(worker, "safe_run_engine", return_value=snapshot["signals"]), \
            patch.object(worker, "generate_market_snapshot", return_value=snapshot), \
            patch.object(worker, "update_paper_trading_from_snapshot") as paper, \
            patch.object(worker, "update_signal_outcome_audit_from_snapshot") as outcome, \
            patch.object(worker, "dispatch_signal_pushes"), \
            patch.object(worker, "send_bulk_alert"), \
            patch.object(worker, "_prewarm_public_quotes"), \
            patch.object(worker, "_prewarm_public_charts"), \
            patch.object(worker, "_prewarm_public_news"):
            worker.worker_loop(StopAfterFirst())

        self.assertTrue(paper.called)
        self.assertTrue(outcome.called)


if __name__ == "__main__":
    unittest.main()
