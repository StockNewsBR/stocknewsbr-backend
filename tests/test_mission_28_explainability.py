import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.dependencies as dependencies_module
import app.system.explainability as explainability_module
from app.api import routes_explainability
from app.system.explainability import calculate_explainability, get_explainability_status
from app.system.system_metrics import get_performance_metrics_snapshot


def _signal(**overrides):
    row = {
        "ticker": "F",
        "master_score": 79.0,
        "master_direction": "BULLISH",
        "master_summary": "Viés comprador: fluxo, tendência e smart money alinhados.",
        "master_risk": "Baixo",
        "final_decision": "OPORTUNIDADE EM FORMAÇÃO",
        "final_decision_reason": "Fluxo comprador com confirmação operacional pendente.",
        "conviction_level": "ALTA",
        "priority_level": "ALTA",
        "operational_status": "READY",
        "audit_status": "APPROVED",
        "support": 14.81,
        "resistance": 14.95,
        "master_components": {
            "flow": 82.0,
            "liquidity": 66.0,
            "trend": 74.0,
            "momentum": 58.0,
            "smart_money": 80.0,
            "risk": 32.0,
            "news": 44.0,
            "macro": 35.0,
            "regime": 61.0,
        },
        "master_consensus": {
            "directions": {
                "flow": "BULLISH",
                "liquidity": "NEUTRAL",
                "trend": "BULLISH",
                "momentum": "NEUTRAL",
                "smart_money": "BULLISH",
                "risk": "NEUTRAL",
                "news": "NEUTRAL",
                "macro": "NEUTRAL",
                "regime": "BULLISH",
            }
        },
        "master_reasoning": {
            "flow_reason": "Fluxo comprador institucional.",
            "liquidity_reason": "Liquidez acima da média.",
            "trend_reason": "Estrutura de tendência positiva.",
            "momentum_reason": "Momentum ainda neutro.",
            "smart_money_reason": "Smart Money positivo.",
            "risk_reason": "Risco baixo no snapshot.",
            "news_reason": "Notícias sem catalisador direto.",
            "macro_reason": "Macro ainda neutro.",
            "regime_reason": "Regime favorece continuação.",
        },
        "conviction_factors": ["consenso institucional", "auditor aprovado"],
        "conviction_conflicts": ["confirmação de preço pendente"],
        "priority_factors": ["prioridade alta pela fila institucional"],
        "opinion_change_conditions": ["fluxo vendedor dominante", "queda de liquidez abaixo do limite"],
    }
    row.update(overrides)
    return row


class Mission28ExplainabilityTests(unittest.TestCase):
    def setUp(self):
        self.original_internal_token = dependencies_module.INTERNAL_API_TOKEN
        dependencies_module.INTERNAL_API_TOKEN = "mission28-internal-token-valid-20260701"

    def tearDown(self):
        dependencies_module.INTERNAL_API_TOKEN = self.original_internal_token

    def test_explanation_is_present_for_snapshot_signal(self):
        payload = calculate_explainability({"signals": [_signal()]})

        self.assertEqual(payload["status"], "READY")
        self.assertEqual(payload["metrics"]["explanations"], 1)
        explanation = payload["explanations"][0]
        self.assertEqual(explanation["ticker"], "F")
        self.assertTrue(explanation["why_this_score"]["positive_factors"])
        self.assertIn("confirmação de preço pendente", explanation["why_this_score"]["negative_factors"])

    def test_score_breakdown_has_required_categories_and_valid_percentages(self):
        explanation = calculate_explainability({"signals": [_signal()]})["explanations"][0]
        breakdown = explanation["score_breakdown"]

        self.assertEqual(set(breakdown), {"flow", "liquidity", "regime", "structure", "news", "risk"})
        total = round(sum(item["contribution_pct"] for item in breakdown.values()), 2)
        self.assertEqual(total, 100.0)
        self.assertGreater(breakdown["flow"]["raw_score"], 0)

    def test_change_my_mind_uses_existing_conditions_and_levels(self):
        explanation = calculate_explainability({"signals": [_signal()]})["explanations"][0]
        change_mind = explanation["what_would_change_my_mind"]

        self.assertIn("fluxo vendedor dominante", change_mind)
        self.assertIn("queda de liquidez abaixo do limite", change_mind)
        self.assertIn("Perda do suporte 14.81", change_mind)

    def test_explainability_does_not_call_external_provider(self):
        source = Path(explainability_module.__file__).read_text(encoding="utf-8")
        for forbidden in ("yfinance", "requests.", "httpx", "urlopen", "urllib", "download(", "fetch("):
            self.assertNotIn(forbidden, source)

        with patch("app.market.market_data_loader._get_yfinance", side_effect=AssertionError("provider must not be called")):
            payload = calculate_explainability({"signals": [_signal()]})

        self.assertEqual(payload["metrics"]["explanations"], 1)

    def test_internal_endpoint_requires_token(self):
        app = FastAPI()
        app.include_router(routes_explainability.router)

        response = TestClient(app).get("/internal/explainability")

        self.assertEqual(response.status_code, 403)

    def test_internal_endpoint_returns_consistent_payload(self):
        app = FastAPI()
        app.include_router(routes_explainability.router)

        with patch("app.system.explainability.get_snapshot", return_value={"signals": [_signal()]}):
            response = TestClient(app).get(
                "/internal/explainability",
                headers={"X-Internal-Token": "mission28-internal-token-valid-20260701"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source"], "snapshot_cache")
        self.assertTrue(payload["diagnostic_only"])
        self.assertIn("metrics", payload)
        self.assertIn("explanations", payload)
        self.assertIn("decision_explainability_score", payload["explanations"][0])

    def test_explainability_appears_in_performance_metrics_snapshot(self):
        with patch("app.system.explainability.get_snapshot", return_value={"signals": [_signal()]}):
            get_explainability_status()
        metrics = get_performance_metrics_snapshot()

        self.assertIn("explainability", metrics)
        self.assertEqual(metrics["explainability"]["explanations"], 1)
        self.assertGreater(metrics["explainability"]["average_decision_explainability_score"], 0)


if __name__ == "__main__":
    unittest.main()
