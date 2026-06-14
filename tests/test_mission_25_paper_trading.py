import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_paper_trading
from app.cache import paper_trading_cache as paper_cache_module
from app.cache.paper_trading_cache import PaperTradingCache
from app.dependencies import require_internal_token
from app.system.paper_trading import get_paper_trading_status, update_paper_trading_from_snapshot


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
        "blocked_by_auditor": False,
        "operational_status": "READY",
        "final_decision": "OPORTUNIDADE CONFIRMADA",
        "final_decision_blocks": [],
        "final_decision_confidence": 82.0,
        "conviction_level": "ALTA",
    }


def _snapshot(rows, *, stale=False):
    return {
        "signals": rows,
        "source": "engine",
        "stale": stale,
        "generated_at": 2_000_000_000.0,
        "go_live_ready": True,
        "institutional_certified": True,
        "institutional_consistency_score": 100.0,
        "contract_coverage": {"total": len(rows), "complete": len(rows), "missing": 0, "coverage_pct": 100.0},
    }


class Mission25PaperTradingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.state_path = Path(self.tmp.name) / "paper_trading.json"
        self.original_cache = paper_cache_module.paper_trading_cache
        paper_cache_module.paper_trading_cache = PaperTradingCache(self.state_path)

    def tearDown(self):
        paper_cache_module.paper_trading_cache = self.original_cache
        self.tmp.cleanup()

    def test_does_not_open_trade_with_stale_snapshot(self):
        state = update_paper_trading_from_snapshot(_snapshot([_row("BUY")], stale=True), now=10.0)

        self.assertEqual(state["metrics"]["open_trades"], 0)
        self.assertEqual(state["metrics"]["skipped_reasons"]["snapshot_stale"], 1)

    def test_does_not_open_trade_with_invalid_price(self):
        state = update_paper_trading_from_snapshot(_snapshot([_row("BUY", price=0)]), now=10.0)

        self.assertEqual(state["metrics"]["open_trades"], 0)
        self.assertEqual(state["metrics"]["skipped_reasons"]["invalid_price"], 1)

    def test_does_not_open_trade_with_invalid_data_quality(self):
        state = update_paper_trading_from_snapshot(_snapshot([_row("BUY", data_quality="score_only")]), now=10.0)

        self.assertEqual(state["metrics"]["open_trades"], 0)
        self.assertEqual(state["metrics"]["skipped_reasons"]["data_quality_score_only"], 1)

    def test_opens_simulated_long_with_valid_buy(self):
        state = update_paper_trading_from_snapshot(_snapshot([_row("BUY", symbol="PETR4", price=100)]), now=10.0)

        self.assertEqual(state["metrics"]["open_trades"], 1)
        self.assertEqual(state["positions"][0]["side"], "LONG")
        self.assertEqual(state["positions"][0]["mode"], "PAPER_ONLY")
        self.assertEqual(state["positions"][0]["simulation"], "SIMULATED")

    def test_opens_simulated_short_with_valid_short(self):
        state = update_paper_trading_from_snapshot(_snapshot([_row("SHORT", symbol="VALE3", price=100)]), now=10.0)

        self.assertEqual(state["metrics"]["open_trades"], 1)
        self.assertEqual(state["positions"][0]["side"], "SHORT")

    def test_closes_long_with_valid_sell(self):
        update_paper_trading_from_snapshot(_snapshot([_row("BUY", symbol="PETR4", price=100)]), now=10.0)
        state = update_paper_trading_from_snapshot(_snapshot([_row("SELL", symbol="PETR4", price=110)]), now=20.0)

        self.assertEqual(state["metrics"]["open_trades"], 0)
        self.assertEqual(state["metrics"]["closed_trades"], 1)
        self.assertEqual(state["trades"][0]["return_pct"], 10.0)

    def test_closes_short_with_valid_cover(self):
        update_paper_trading_from_snapshot(_snapshot([_row("SHORT", symbol="VALE3", price=100)]), now=10.0)
        state = update_paper_trading_from_snapshot(_snapshot([_row("COVER", symbol="VALE3", price=90)]), now=20.0)

        self.assertEqual(state["metrics"]["open_trades"], 0)
        self.assertEqual(state["metrics"]["closed_trades"], 1)
        self.assertEqual(state["trades"][0]["return_pct"], 10.0)

    def test_calculates_return_metrics(self):
        update_paper_trading_from_snapshot(_snapshot([_row("BUY", symbol="PETR4", price=100)]), now=10.0)
        update_paper_trading_from_snapshot(_snapshot([_row("SELL", symbol="PETR4", price=120)]), now=20.0)
        update_paper_trading_from_snapshot(_snapshot([_row("SHORT", symbol="VALE3", price=100)]), now=30.0)
        state = update_paper_trading_from_snapshot(_snapshot([_row("COVER", symbol="VALE3", price=110)]), now=40.0)

        self.assertEqual(state["metrics"]["closed_trades"], 2)
        self.assertEqual(state["metrics"]["win_rate"], 50.0)
        self.assertEqual(state["metrics"]["avg_return_pct"], 5.0)
        self.assertEqual(state["metrics"]["total_return_pct"], 10.0)
        self.assertEqual(state["metrics"]["max_win_pct"], 20.0)
        self.assertEqual(state["metrics"]["max_loss_pct"], -10.0)

    def test_persists_paper_trading_json(self):
        update_paper_trading_from_snapshot(_snapshot([_row("BUY")]), now=10.0)

        self.assertTrue(self.state_path.exists())
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["mode"], "PAPER_ONLY")
        self.assertEqual(payload["simulation"], "SIMULATED")
        self.assertEqual(payload["metrics"]["open_trades"], 1)

    def test_recovers_state_after_reload(self):
        update_paper_trading_from_snapshot(_snapshot([_row("BUY")]), now=10.0)
        reloaded = PaperTradingCache(self.state_path).get()

        self.assertEqual(reloaded["positions"][0]["symbol"], "PETR4")
        self.assertEqual(reloaded["metrics"]["open_trades"], 1)

    def test_tolerates_missing_and_corrupted_state_file(self):
        missing = PaperTradingCache(Path(self.tmp.name) / "missing.json").get()
        self.assertEqual(missing["metrics"]["total_trades"], 0)

        self.state_path.write_text("{broken", encoding="utf-8")
        corrupted = PaperTradingCache(self.state_path).get()
        self.assertEqual(corrupted["paper_trading_status"], "DEGRADED")
        self.assertEqual(corrupted["state_error"], "state_file_corrupted")

    def test_metrics_do_not_break_with_zero_trades(self):
        status = get_paper_trading_status()

        self.assertEqual(status["metrics"]["total_trades"], 0)
        self.assertEqual(status["metrics"]["win_rate"], 0.0)
        self.assertEqual(status["metrics"]["skipped_reasons"], {})

    def test_passive_decisions_are_skipped(self):
        rows = [_row(decision, symbol=f"TST{index}") for index, decision in enumerate(("NO_TRADE", "DO_NOT_TRADE", "WAIT", "HOLD"), start=1)]
        state = update_paper_trading_from_snapshot(_snapshot(rows), now=10.0)

        self.assertEqual(state["metrics"]["open_trades"], 0)
        self.assertEqual(state["metrics"]["skipped_reasons"]["decision_not_actionable"], 4)

    def test_internal_endpoint_returns_paper_only_simulated_payload(self):
        update_paper_trading_from_snapshot(_snapshot([_row("BUY")]), now=10.0)
        app = FastAPI()
        app.include_router(routes_paper_trading.router)
        app.dependency_overrides[require_internal_token] = lambda: True

        response = TestClient(app).get("/internal/paper-trading")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["paper_only"])
        self.assertEqual(payload["mode"], "PAPER_ONLY")
        self.assertEqual(payload["simulation"], "SIMULATED")
        self.assertEqual(payload["open_trades"], 1)

    def test_does_not_mutate_go_live_certification_fields(self):
        snapshot = _snapshot([_row("BUY")])
        expected = {
            "go_live_ready": snapshot["go_live_ready"],
            "institutional_certified": snapshot["institutional_certified"],
            "institutional_consistency_score": snapshot["institutional_consistency_score"],
            "contract_coverage": dict(snapshot["contract_coverage"]),
        }

        update_paper_trading_from_snapshot(snapshot, now=10.0)

        self.assertEqual(snapshot["go_live_ready"], expected["go_live_ready"])
        self.assertEqual(snapshot["institutional_certified"], expected["institutional_certified"])
        self.assertEqual(snapshot["institutional_consistency_score"], expected["institutional_consistency_score"])
        self.assertEqual(snapshot["contract_coverage"], expected["contract_coverage"])

    def test_does_not_call_external_provider(self):
        with patch("app.market.market_data_loader._get_yfinance", side_effect=AssertionError("provider must not be called")):
            state = update_paper_trading_from_snapshot(_snapshot([_row("BUY")]), now=10.0)

        self.assertEqual(state["metrics"]["open_trades"], 1)


if __name__ == "__main__":
    unittest.main()
