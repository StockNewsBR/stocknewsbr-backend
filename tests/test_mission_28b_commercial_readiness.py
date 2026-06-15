import unittest
from unittest.mock import patch

from app.services.ranking import _normalize_snapshot_ranking
from app.services.score_display import attach_master_score_display_contract, normalize_master_score_display
from app.services.snapshot_contract import snapshot_row_summary
from app.system.explainability import explain_signal
from app.system.performance_intelligence import score_bucket


def _actionable_row(master_score):
    return {
        "ticker": "F",
        "symbol": "F",
        "score": master_score,
        "master_score": master_score,
        "signal": "BUY",
        "trade_action": "BUY",
        "decision_ready": True,
        "decision_state": "BUY_READY",
        "price": 14.84,
        "volume": 1_000_000,
        "data_quality": "valid",
        "audit_status": "APPROVED",
        "master_status": "APPROVED",
        "master_direction": "BULLISH",
        "ranking_opportunity_score": 88.0,
        "ranking_eligible": True,
    }


class Mission28BCommercialReadinessTests(unittest.TestCase):
    def test_master_score_display_normalizes_raw_above_ten(self):
        self.assertEqual(normalize_master_score_display(-2)[0], 0.0)
        self.assertEqual(normalize_master_score_display(11.7)[0], 1.2)
        self.assertEqual(normalize_master_score_display(12.0)[0], 1.2)
        self.assertEqual(normalize_master_score_display(15.0)[0], 1.5)
        self.assertEqual(normalize_master_score_display(87.0)[0], 8.7)
        self.assertEqual(normalize_master_score_display(79.0)[0], 7.9)
        self.assertEqual(normalize_master_score_display(120.0)[0], 10.0)
        self.assertEqual(normalize_master_score_display(10.0)[0], 10.0)
        self.assertEqual(normalize_master_score_display(0)[0], 0.0)

    def test_snapshot_contract_exposes_display_safe_score(self):
        payload = snapshot_row_summary(_actionable_row(12.0))

        self.assertEqual(payload["master_score"], 1.2)
        self.assertEqual(payload["master_score_raw"], 12.0)
        self.assertEqual(payload["master_score_display"], 1.2)
        self.assertEqual(payload["master_score_display_warning"], "master_score_normalized_from_raw_100")

    def test_ranking_exposes_display_safe_score_without_changing_raw_score(self):
        with patch("app.services.ranking.get_snapshot_info", return_value={"signals": 1, "age_seconds": 1}), \
             patch("app.services.ranking.get_snapshot_signals", return_value=[_actionable_row(12.0)]), \
             patch("app.services.ranking.ensure_final_decision_rows", side_effect=lambda rows: rows), \
             patch("app.services.ranking.ensure_institutional_priority_rows", side_effect=lambda rows: rows), \
             patch("app.services.ranking.ensure_institutional_conviction_rows", side_effect=lambda rows: rows), \
             patch("app.services.ranking.ensure_operational_rules_rows", side_effect=lambda rows: rows), \
             patch("app.services.ranking.ensure_historical_confidence_rows", side_effect=lambda rows: rows), \
             patch("app.services.ranking.ensure_institutional_ranking_rows", side_effect=lambda rows: rows), \
             patch("app.services.ranking.institutional_ranking_items", side_effect=lambda rows, limit=200: rows):
            payload = _normalize_snapshot_ranking()

        self.assertEqual(payload[0]["score"], 12.0)
        self.assertEqual(payload[0]["master_score"], 1.2)
        self.assertEqual(payload[0]["master_score_raw"], 12.0)
        self.assertEqual(payload[0]["master_score_display"], 1.2)
        self.assertEqual(payload[0]["master_score_display_warning"], "master_score_normalized_from_raw_100")

    def test_explainability_exposes_display_safe_score(self):
        payload = explain_signal(_actionable_row(12.0))

        self.assertEqual(payload["master_score"], 1.2)
        self.assertEqual(payload["master_score_raw"], 12.0)
        self.assertEqual(payload["master_score_display"], 1.2)
        self.assertEqual(payload["master_score_display_warning"], "master_score_normalized_from_raw_100")

    def test_performance_intelligence_keeps_score_bucket_bounded(self):
        self.assertEqual(score_bucket({"master_score_raw": 87.0}), "8-10")
        self.assertEqual(score_bucket({"master_score": 12.0}), "0-4")
        self.assertEqual(score_bucket({"master_score": 120.0}), "8-10")

    def test_warning_is_appended_without_dropping_existing_warnings(self):
        payload = attach_master_score_display_contract({"master_score": 12.0, "warnings": ["existing"]})

        self.assertIn("existing", payload["warnings"])
        self.assertIn("master_score_normalized_from_raw_100", payload["warnings"])


if __name__ == "__main__":
    unittest.main()
