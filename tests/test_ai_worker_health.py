import unittest
from unittest.mock import patch

from app.system import ai_worker


class AiWorkerHealthTests(unittest.TestCase):
    def test_marks_degraded_when_snapshot_and_signals_are_empty(self):
        bootstrap = {
            "primary_launch_platform": "google_app",
            "subscription_unlocks": ["google_app", "website", "telegram"],
        }

        with patch.object(ai_worker, "ensure_runtime_schema"), patch.object(
            ai_worker,
            "get_all_signals",
            return_value=[],
        ), patch.object(
            ai_worker,
            "get_signal_info",
            return_value={"signals": 0, "timestamp": None, "age_seconds": None},
        ), patch.object(
            ai_worker,
            "get_snapshot_info",
            return_value={"signals": 0, "timestamp": None, "age_seconds": None},
        ), patch.object(
            ai_worker,
            "get_metrics_snapshot",
            return_value={},
        ), patch.object(
            ai_worker,
            "_import_health",
            return_value={"ok": [], "failed": []},
        ), patch.object(
            ai_worker,
            "_snapshot_self_heal",
            return_value={"rebuilt_snapshot": False, "snapshot_info": {"signals": 0, "timestamp": None, "age_seconds": None}},
        ), patch.object(
            ai_worker,
            "generate_weekly_polls_for_top_symbols",
            return_value=[],
        ), patch.object(
            ai_worker,
            "get_public_bootstrap",
            return_value=bootstrap,
        ), patch.object(
            ai_worker,
            "_write_report",
        ), patch.object(
            ai_worker,
            "_record_report",
        ):
            report = ai_worker.run_ai_worker_cycle()

        self.assertEqual(report["status"], "degraded")
        self.assertIn("signals_empty", report["health_flags"])
        self.assertIn("snapshot_empty", report["health_flags"])


if __name__ == "__main__":
    unittest.main()
