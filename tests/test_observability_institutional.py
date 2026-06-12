import unittest
from unittest.mock import patch

from app.api import routes_system
from app.services import workspace_service
from app.system.observability_engine import build_observability_dashboard, record_observability_event


class ObservabilityInstitutionalTests(unittest.TestCase):
    def test_build_observability_dashboard_exposes_health_center_and_error_center(self):
        dashboard = build_observability_dashboard(
            snapshot={"signals": 12, "invalid": 1, "discarded": 0, "blocked": 2, "master_scores": [{"direction": "BULLISH"}]},
            ai_worker={"status": "warning"},
            ai_tabs={"overall_status": "ok", "batch_summary": {"approved_tools": 7, "blocked_tools": 1}},
            polls={"current_week_polls": 3},
            providers={"items": [{"provider": "Yahoo", "status": "HEALTHY"}, {"provider": "Polygon", "status": "DEGRADED"}]},
            ranking={"status": "HEALTHY", "eligible": 5, "discarded": 1, "blocked": 2},
            radar={"status": "HEALTHY", "generated": 8, "filtered": 3, "blocked": 1},
            telegram={"status": "HEALTHY", "sent": 4, "blocked": 1, "discarded": 0, "errors": 0},
            system_status={"status": "HEALTHY"},
        )

        self.assertIn(dashboard["system_status"], {"HEALTHY", "DEGRADED", "CRITICAL"})
        self.assertIn("providers", dashboard)
        self.assertIn("recent_errors", dashboard)
        self.assertIn("error_center", dashboard)
        self.assertGreaterEqual(len(dashboard["alerts"]), 1)

    def test_routes_system_observability_dashboard_endpoint_returns_dashboard(self):
        with patch.object(routes_system, "get_snapshot_info", return_value={"signals": 9, "invalid": 0, "discarded": 0, "blocked": 0, "master_scores": []}), \
            patch.object(routes_system, "get_ai_worker_report", return_value={"status": "ok", "snapshot_health": {"source": "current", "cooldown_remaining_seconds": 0}}), \
            patch.object(routes_system, "get_ai_tab_audit_report", return_value={"overall_status": "ok", "batch_summary": {"approved_tools": 8, "blocked_tools": 0}}), \
            patch.object(routes_system, "get_poll_store_summary", return_value={"current_week_polls": 2}), \
            patch.object(routes_system, "get_push_status", return_value={"android_ready": True, "registered_tokens": 11}), \
            patch.object(routes_system, "get_storage_status", return_value={"ready": True}), \
            patch.object(routes_system, "get_ranking", return_value=[{"symbol": "PETR4"}]):
            dashboard = routes_system.observability_dashboard()

        self.assertIn("system_status", dashboard)
        self.assertIn("providers", dashboard)
        self.assertIn("error_center", dashboard)
        self.assertIn("alerts", dashboard)

    def test_workspace_consumes_observability_contract(self):
        with patch.object(workspace_service.routes_system, "observability_dashboard", return_value={
            "system_status": "DEGRADED",
            "providers": {"items": [{"provider": "Yahoo", "status": "DEGRADED"}]},
            "snapshot_health": {"status": "DEGRADED", "signals_generated": 0},
            "auditor_health": {"status": "CAUTION", "blocked_ratio": 0.5},
            "score_health": {"status": "DEGRADED", "distribution": {"BULLISH": 1}},
            "radar_health": {"status": "DEGRADED", "generated": 0, "blocked": 0},
            "ranking_health": {"status": "DEGRADED", "eligible": 0},
            "telegram_health": {"status": "DEGRADED", "sent": 0},
            "recent_errors": [{"kind": "provider", "message": "timeout"}],
            "alerts": [{"kind": "provider", "message": "provider degradado", "severity": "warning"}],
        }), patch.object(workspace_service, "get_public_bootstrap", return_value={"brand": {}, "pricing": {}, "launch_roadmap": {}, "ai_modules": {}, "social_features": {}}), patch.object(workspace_service, "get_help_center_blueprint", return_value={"guides": []}), patch.object(workspace_service, "get_media_status", return_value={"provider": "local"}), patch.object(workspace_service, "get_push_status", return_value={"android_ready": True}), patch.object(workspace_service, "get_metrics_snapshot", return_value={"engine_cycles": 1, "signals_generated": 0, "assets_scanned": 0, "cache_age": 0, "http_requests": 0, "ws_connections": 0, "chat_messages": 0}), patch.object(workspace_service, "get_ranking", return_value=[]), patch.object(workspace_service, "get_posts", return_value=[]), patch.object(workspace_service, "get_user_workspace_layout", return_value={"tabs": [], "pinned_ticker": "PETR4"}), patch.object(workspace_service, "get_snapshot", return_value={"signals": [], "symbol_snapshots": {}, "strategic_panel_summary": ""}), patch.object(workspace_service, "list_room_messages", return_value=[]), patch.object(workspace_service, "persist_ai_alert_history", side_effect=lambda value: value):
            payload = workspace_service.get_workspace_data(user_id=7, channel="web")

        self.assertIn("observability", payload)
        self.assertEqual(payload["observability"]["system_status"], "DEGRADED")


if __name__ == "__main__":
    unittest.main()
