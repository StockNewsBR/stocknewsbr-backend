import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.dependencies as dependencies_module
import app.system.performance_intelligence as performance_intelligence_module
from app.api import routes_performance_intelligence
from app.cache import signal_outcome_cache as outcome_cache_module
from app.cache.signal_outcome_cache import SignalOutcomeCache, update_signal_outcome_state
from app.system.performance_intelligence import get_performance_intelligence_status
from app.system.system_metrics import get_performance_metrics_snapshot


def _record(
    ticker: str,
    result: str,
    *,
    actionability: bool = True,
    status: str | None = None,
    master_score: float = 8.0,
    regime: str = "bullish",
    return_pct: float = 1.0,
    mfe_pct: float | None = None,
    mae_pct: float | None = None,
):
    resolved_status = status or (result if actionability else "blocked")
    return {
        "ticker": ticker,
        "symbol": ticker,
        "actionability": actionability,
        "status": resolved_status,
        "simulated_result": result,
        "master_score": master_score,
        "market_regime": regime,
        "outcome_return_pct": return_pct,
        "mfe_pct": mfe_pct if mfe_pct is not None else max(return_pct, 0.0),
        "mae_pct": mae_pct if mae_pct is not None else min(return_pct, 0.0),
        "mode": "PAPER_ONLY",
        "simulation": "SIMULATED",
    }


def _sample_records():
    return [
        _record("PETR4", "winner", master_score=8.5, regime="bullish", return_pct=2.0, mfe_pct=3.0, mae_pct=-0.5),
        _record("PETR4", "loser", master_score=5.5, regime="sideways", return_pct=-1.0, mfe_pct=0.4, mae_pct=-2.0),
        _record("VALE3", "neutral", master_score=6.5, regime="bearish", return_pct=0.0),
        _record("BBDC4", "winner", actionability=False, status="blocked", master_score=7.5, regime="low liquidity", return_pct=1.2),
        _record("BBDC4", "loser", actionability=False, status="blocked", master_score=4.5, regime="volatile", return_pct=-0.8),
        _record("ITUB4", "neutral", actionability=False, status="blocked", master_score=3.5, regime="lateral", return_pct=0.0),
        _record("TSLA", "winner", master_score=9.0, regime="uptrend", return_pct=3.0, mfe_pct=4.0, mae_pct=-0.2),
    ]


class Mission27PerformanceIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.outcome_state_path = Path(self.tmp.name) / "signal_outcomes.json"
        self.original_outcome_cache = outcome_cache_module.signal_outcome_cache
        self.original_internal_token = dependencies_module.INTERNAL_API_TOKEN
        outcome_cache_module.signal_outcome_cache = SignalOutcomeCache(self.outcome_state_path)
        dependencies_module.INTERNAL_API_TOKEN = "mission27-internal-token-valid-20260701"

    def tearDown(self):
        outcome_cache_module.signal_outcome_cache = self.original_outcome_cache
        dependencies_module.INTERNAL_API_TOKEN = self.original_internal_token
        self.tmp.cleanup()

    def _load_records(self, records=None):
        return update_signal_outcome_state(
            {
                "mode": "PAPER_ONLY",
                "simulation": "SIMULATED",
                "records": records if records is not None else _sample_records(),
            }
        )

    def test_score_buckets_are_calculated_on_master_score_scale(self):
        self._load_records()
        payload = get_performance_intelligence_status()

        self.assertEqual(payload["by_score_bucket"]["0-4"]["sample_size"], 1)
        self.assertEqual(payload["by_score_bucket"]["4-5"]["sample_size"], 1)
        self.assertEqual(payload["by_score_bucket"]["5-6"]["sample_size"], 1)
        self.assertEqual(payload["by_score_bucket"]["6-7"]["sample_size"], 1)
        self.assertEqual(payload["by_score_bucket"]["7-8"]["sample_size"], 1)
        self.assertEqual(payload["by_score_bucket"]["8-10"]["sample_size"], 2)

    def test_regime_buckets_are_normalized(self):
        self._load_records()
        payload = get_performance_intelligence_status()

        self.assertEqual(payload["by_regime"]["bullish"]["sample_size"], 2)
        self.assertEqual(payload["by_regime"]["bearish"]["sample_size"], 1)
        self.assertEqual(payload["by_regime"]["sideways"]["sample_size"], 2)
        self.assertEqual(payload["by_regime"]["volatile"]["sample_size"], 1)
        self.assertEqual(payload["by_regime"]["low_liquidity"]["sample_size"], 1)

    def test_asset_buckets_are_calculated(self):
        self._load_records()
        payload = get_performance_intelligence_status()

        self.assertEqual(payload["by_asset"]["PETR4"]["sample_size"], 2)
        self.assertEqual(payload["by_asset"]["BBDC4"]["blocked_would_have_won"], 1)
        self.assertEqual(payload["by_asset"]["TSLA"]["released_won"], 1)

    def test_blocked_would_have_won_is_separate(self):
        self._load_records()
        payload = get_performance_intelligence_status()

        self.assertEqual(payload["blocked_would_have_won"], 1)
        self.assertEqual(payload["auditor_efficiency"]["blocked_would_have_won"], 1)

    def test_blocked_correctly_is_separate(self):
        self._load_records()
        payload = get_performance_intelligence_status()

        self.assertEqual(payload["blocked_correctly"], 2)
        self.assertEqual(payload["auditor_efficiency"]["blocked_correctly"], 2)
        self.assertEqual(payload["auditor_efficiency"]["institutional_auditor_efficiency"], 66.67)

    def test_released_failed_is_separate(self):
        self._load_records()
        payload = get_performance_intelligence_status()

        self.assertEqual(payload["released_failed"], 1)
        self.assertEqual(payload["by_asset"]["PETR4"]["released_failed"], 1)

    def test_released_won_is_separate(self):
        self._load_records()
        payload = get_performance_intelligence_status()

        self.assertEqual(payload["released_won"], 2)
        self.assertEqual(payload["by_score_bucket"]["8-10"]["released_won"], 2)

    def test_internal_endpoint_requires_token(self):
        app = FastAPI()
        app.include_router(routes_performance_intelligence.router)

        response = TestClient(app).get("/internal/performance-intelligence")

        self.assertEqual(response.status_code, 403)

    def test_internal_endpoint_returns_expected_payload(self):
        self._load_records()
        app = FastAPI()
        app.include_router(routes_performance_intelligence.router)

        response = TestClient(app).get(
            "/internal/performance-intelligence",
            headers={"X-Internal-Token": "mission27-internal-token-valid-20260701"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "READY")
        self.assertEqual(payload["sample_size"], 7)
        self.assertIn("by_asset", payload)
        self.assertIn("by_regime", payload)
        self.assertIn("by_score_bucket", payload)
        self.assertIn("auditor_efficiency", payload)
        self.assertTrue(payload["diagnostic_only"])

    def test_performance_intelligence_does_not_call_external_provider(self):
        source = Path(performance_intelligence_module.__file__).read_text(encoding="utf-8")
        for forbidden in ("yfinance", "requests.", "httpx", "urlopen", "urllib", "download(", "fetch("):
            self.assertNotIn(forbidden, source)

        self._load_records()
        with patch("app.market.market_data_loader._get_yfinance", side_effect=AssertionError("provider must not be called")):
            payload = get_performance_intelligence_status()

        self.assertEqual(payload["sample_size"], 7)

    def test_insufficient_sample_when_sample_is_small(self):
        self._load_records([_record("PETR4", "winner", master_score=8.0)])
        payload = get_performance_intelligence_status()

        self.assertEqual(payload["status"], "INSUFFICIENT_SAMPLE")
        self.assertEqual(payload["auditor_efficiency"]["status"], "insufficient_sample")
        self.assertIn("Amostra insuficiente", payload["recommendations"][0])

    def test_recommendations_do_not_change_rules(self):
        self._load_records()
        payload = get_performance_intelligence_status()

        self.assertTrue(payload["diagnostic_only"])
        self.assertNotIn("threshold_changes", payload)
        self.assertNotIn("rule_changes", payload)
        self.assertTrue(any("Nao altera thresholds" in item or "não alterar thresholds" in item for item in payload["limitations"]))

    def test_performance_intelligence_appears_in_metrics_snapshot(self):
        self._load_records()
        get_performance_intelligence_status()
        metrics = get_performance_metrics_snapshot()

        self.assertIn("performance_intelligence", metrics)
        self.assertEqual(metrics["performance_intelligence"]["sample_size"], 7)
        self.assertEqual(metrics["performance_intelligence"]["released_won"], 2)


if __name__ == "__main__":
    unittest.main()
