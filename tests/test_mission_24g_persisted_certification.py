import json
import os
import time
import unittest
from unittest.mock import patch

from app.api import routes_system
from app.cache.snapshot_cache import SnapshotCache


def _certifiable_row(ticker="PETR4"):
    return {
        "ticker": ticker,
        "symbol": ticker,
        "score": 91.0,
        "signal": "BUY",
        "trade_action": "BUY",
        "decision_ready": True,
        "decision_state": "BUY_READY",
        "can_trade": True,
        "data_quality": "priced",
        "price": 37.5,
        "volume": 1_800_000,
        "audit_status": "APPROVED",
        "auditor_status": "APPROVED",
        "blocked_by_auditor": False,
        "master_score": 92.0,
        "master_direction": "BULLISH",
        "master_status": "APPROVED",
        "master_conviction": "Alta",
        "master_confidence": "Alta",
        "strategic_panel": {
            "recommended_action": "OPORTUNIDADE CONFIRMADA",
            "strategic_panel_summary": "Contexto institucional favoravel.",
        },
        "historical_confidence_score": 74.0,
        "operational_status": "READY",
        "operational_ready": True,
        "operational_blocks": [],
        "conviction_level": "MUITO ALTA",
        "priority_level": "CRÍTICA",
        "ranking_eligible": True,
        "radar_no_trade_now": False,
        "final_decision": "🟢 OPORTUNIDADE CONFIRMADA",
        "final_decision_blocks": [],
    }


def _metrics():
    return {
        "engine_cycles": 1,
        "scan_time": 0.1,
        "signals_generated": 1,
        "assets_scanned": 1,
        "cache_age": 0,
        "workers": 1,
        "http_requests": 0,
        "http_errors": 0,
        "ws_connections": 0,
        "chat_messages": 0,
        "reports_created": 0,
        "uploads_completed": 0,
        "push_sends": 0,
        "worker_runtime": {},
        "institutional_metrics": {},
    }


class Mission24GPersistedCertificationTests(unittest.TestCase):
    def test_snapshot_cache_persists_institutional_certification_contract(self):
        generated_at = time.time()
        payload_without_certification = {
            "signals": [_certifiable_row()],
            "source": "engine",
            "stale": False,
            "generated_at": generated_at,
            "go_live_ready": True,
        }

        with patch.dict(os.environ, {"STOCKNEWSBR_TEST_MODE": "1", "SNAPSHOT_CACHE_FILE": ""}):
            cache = SnapshotCache()
            cache.update(payload_without_certification)
            persisted = json.loads(cache._storage_path.read_text(encoding="utf-8"))
            payload = persisted["payload"]

        self.assertTrue(payload["go_live_ready"])
        self.assertTrue(payload["institutional_certified"])
        self.assertEqual(payload["institutional_consistency_score"], 100.0)
        self.assertEqual(payload["contract_coverage"]["coverage_pct"], 100.0)
        self.assertEqual(payload["contract_coverage"]["total"], 1)
        self.assertIn("certification_timestamp", payload)
        self.assertEqual(payload["certification_reasons"], [])

    def test_system_status_and_readiness_match_persisted_go_live_contract(self):
        generated_at = time.time()
        payload = {
            "signals": [_certifiable_row()],
            "source": "engine",
            "stale": False,
            "generated_at": generated_at,
        }

        with patch.dict(os.environ, {"STOCKNEWSBR_TEST_MODE": "1", "SNAPSHOT_CACHE_FILE": ""}):
            cache = SnapshotCache()
            cache.update(payload)
            snapshot = cache.get()
            snapshot_info = cache.info()

        metrics = _metrics()
        with patch.object(routes_system, "get_snapshot", return_value=snapshot), patch.object(
            routes_system, "get_snapshot_info", return_value=snapshot_info
        ), patch.object(routes_system, "get_metrics_snapshot", return_value=metrics), patch.object(
            routes_system, "get_storage_status", return_value={"ready": True}
        ), patch.object(routes_system, "get_media_status", return_value={"cdn_ready": True}), patch.object(
            routes_system, "get_push_status", return_value={"android_ready": True, "apple_ready": False}
        ), patch.object(routes_system, "get_moderation_summary", return_value={}):
            status = routes_system.system_status()
            readiness = routes_system.system_readiness()

        self.assertEqual(snapshot["go_live_ready"], status["go_live_ready"])
        self.assertEqual(status["go_live_ready"], readiness["go_live_ready"])
        self.assertEqual(snapshot["institutional_certified"], status["institutional_certified"])
        self.assertEqual(status["institutional_certified"], readiness["institutional_certified"])
        self.assertEqual(snapshot["contract_coverage"], status["contract_coverage"])
        self.assertEqual(status["contract_coverage"], readiness["contract_coverage"])


if __name__ == "__main__":
    unittest.main()
