import unittest
from unittest.mock import patch

from app.api import routes_system
from app.system.system_metrics import (
    format_prometheus_metrics,
    get_performance_metrics_snapshot,
    record_external_provider_call,
    record_signal_quality_coverage,
)


class SystemHealthRouteTests(unittest.TestCase):
    def test_system_health_combines_worker_snapshot_audit_and_polls(self):
        with patch.object(
            routes_system,
            "get_ai_worker_report",
            return_value={
                "status": "warning",
                "snapshot_health": {"source": "last_good", "cooldown_remaining_seconds": 42},
            },
        ), patch.object(
            routes_system,
            "get_ai_tab_audit_report",
            return_value={
                "overall_status": "ok",
                "release_decision": {"go_live": True},
                "batch_summary": {"approved_tools": 10},
            },
        ), patch.object(
            routes_system,
            "get_snapshot_info",
            return_value={"signals": 8, "timestamp": 1713866400.0, "age_seconds": 12, "has_signals": True, "is_empty": False},
        ), patch.object(
            routes_system,
            "get_poll_store_summary",
            return_value={"polls": 12, "symbols": 6, "current_week_polls": 4, "week_key": "2026-W17", "store_path": "runtime/polls/weekly_polls.json"},
        ):
            health = routes_system.system_health()

        self.assertEqual(health["status"], "warning")
        self.assertEqual(health["snapshot"]["signals"], 8)
        self.assertEqual(health["worker"]["snapshot_source"], "last_good")
        self.assertEqual(health["audit"]["approved_tools"], 10)
        self.assertEqual(health["polls"]["current_week_polls"], 4)

    def test_system_health_reports_degraded_when_snapshot_is_empty(self):
        with patch.object(
            routes_system,
            "get_ai_worker_report",
            return_value={
                "status": "ok",
                "snapshot_health": {"source": "current", "cooldown_remaining_seconds": 0},
            },
        ), patch.object(
            routes_system,
            "get_ai_tab_audit_report",
            return_value={
                "overall_status": "ok",
                "release_decision": {"go_live": False},
                "batch_summary": {"approved_tools": 0},
            },
        ), patch.object(
            routes_system,
            "get_snapshot_info",
            return_value={"signals": 0, "timestamp": None, "age_seconds": None, "has_signals": False, "is_empty": True},
        ), patch.object(
            routes_system,
            "get_poll_store_summary",
            return_value={"polls": 12, "symbols": 6, "current_week_polls": 4, "week_key": "2026-W17", "store_path": "runtime/polls/weekly_polls.json"},
        ):
            health = routes_system.system_health()

        self.assertEqual(health["status"], "degraded")

    def test_metrics_include_signal_quality_coverage(self):
        record_signal_quality_coverage(
            [
                {"ticker": "PETR4", "price": 37.5, "volume": 1_000_000, "data_quality": "priced", "decision_ready": True},
                {"ticker": "VALE3", "score": 88, "data_quality": "score_only", "conflict_detected": True},
            ],
            source="unit_test",
        )

        performance = get_performance_metrics_snapshot()
        coverage = performance["signal_quality_coverage"]["unit_test"]

        self.assertEqual(coverage["total"], 2)
        self.assertEqual(coverage["with_price"], 1)
        self.assertEqual(coverage["with_volume"], 1)
        self.assertEqual(coverage["score_only"], 1)
        self.assertIn('signal_quality_coverage_ratio{source="unit_test",field="price"}', format_prometheus_metrics())

    def test_metrics_include_external_provider_symbol_calls(self):
        record_external_provider_call(
            "yfinance",
            "download",
            duration_seconds=0.12,
            success=True,
            source="unit_test",
            symbol="PETR4",
        )

        performance = get_performance_metrics_snapshot()
        symbol_metrics = performance["external_provider_symbol_call_total"]

        self.assertIn("unit_test:yfinance:download:success:PETR4", symbol_metrics)
        self.assertEqual(symbol_metrics["unit_test:yfinance:download:success:PETR4"]["count"], 1)
        self.assertIn(
            'external_provider_symbol_call_total{source="unit_test",provider="yfinance",operation="download",outcome="success",symbol="PETR4"}',
            format_prometheus_metrics(),
        )


if __name__ == "__main__":
    unittest.main()
