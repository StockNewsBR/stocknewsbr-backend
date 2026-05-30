import unittest
from unittest.mock import patch

import worker
from app.system import ai_worker
from app.system import snapshot_worker
from app.cache.snapshot_cache import SnapshotCache


class AiWorkerHealthTests(unittest.TestCase):
    def test_marks_warning_when_snapshot_and_signals_are_empty(self):
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
            return_value={
                "rebuilt_snapshot": False,
                "snapshot_info": {"signals": 0, "timestamp": None, "age_seconds": None, "has_signals": False, "is_empty": True},
                "snapshot": {"signals": []},
                "source": "current",
                "reason": "signal_cache_empty_alert_only",
                "last_good_snapshot": {},
            },
        ), patch.object(
            ai_worker,
            "generate_weekly_polls_for_top_symbols",
            return_value=[],
        ), patch.object(
            ai_worker,
            "run_ai_tab_audit",
            return_value={"overall_status": "ok", "coverage": {}, "available_tools": [], "benchmark": {}, "batch_summary": {}, "release_decision": {}},
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

        self.assertEqual(report["status"], "warning")
        self.assertIn("signals_empty", report["health_flags"])
        self.assertIn("snapshot_empty", report["health_flags"])
        self.assertEqual(report["decision"]["severity"], "warning")

    def test_snapshot_self_heal_prefers_last_good_snapshot(self):
        last_good = {
            "signals": [
                {"ticker": "PETR4", "score": 88.0},
            ],
            "generated_at": "2026-04-23T10:00:00Z",
            "updated_at": 1713866400.0,
        }

        with patch.object(ai_worker, "get_snapshot", return_value={"signals": []}), patch.object(
            ai_worker,
            "get_last_good_snapshot",
            return_value=last_good,
        ), patch.object(
            ai_worker,
            "generate_market_snapshot",
        ) as rebuild:
            healed = ai_worker._snapshot_self_heal([], {"signals": 0, "timestamp": None, "age_seconds": None})

        self.assertFalse(rebuild.called)
        self.assertEqual(healed["source"], "last_good")
        self.assertEqual(healed["snapshot_info"]["signals"], 1)
        self.assertTrue(healed["snapshot_info"]["has_signals"])

    def test_snapshot_self_heal_honors_rebuild_cooldown(self):
        with patch.object(
            ai_worker,
            "get_snapshot",
            return_value={"signals": [], "stale": True, "source": "engine"},
        ), patch.object(
            ai_worker,
            "get_last_good_snapshot",
            return_value={"signals": [{"ticker": "PETR4", "score": 88.0}], "stale": False, "source": "signal_cache"},
        ), patch.object(
            ai_worker,
            "generate_market_snapshot",
        ) as rebuild:
            ai_worker._snapshot_health_cache["timestamp"] = 1000.0
            ai_worker._snapshot_health_cache["mode"] = "rebuilt"
            ai_worker._snapshot_health_cache["reason"] = "fresh_signals_available"
            with patch("app.system.ai_worker.time.time", return_value=1001.0):
                healed = ai_worker._snapshot_self_heal(
                    [{"ticker": "VALE3", "score": 91.0}],
                    {"signals": 0, "timestamp": None, "age_seconds": None},
                )

        self.assertFalse(rebuild.called)
        self.assertEqual(healed["source"], "last_good")
        self.assertGreater(healed["cooldown_remaining_seconds"], 0)

    def test_snapshot_cache_only_promotes_fresh_non_stale_payloads(self):
        cache = SnapshotCache()
        cache.update({"signals": [{"ticker": "PETR4", "score": 88.0}], "source": "signal_cache", "stale": False})
        cache.update({"signals": [{"ticker": "VALE3", "score": 70.0}], "source": "snapshot_fallback", "stale": True})

        last_good = cache.get_last_good()

        self.assertEqual(last_good["signals"][0]["ticker"], "PETR4")
        self.assertEqual(last_good.get("source"), "signal_cache")

    def test_worker_loop_refreshes_snapshot_even_without_signals(self):
        class SingleCycleStopEvent:
            def __init__(self):
                self.wait_calls = 0

            def is_set(self):
                return self.wait_calls > 0

            def wait(self, timeout):
                self.wait_calls += 1
                return True

        stop_event = SingleCycleStopEvent()

        with patch.object(worker, "safe_run_engine", return_value=[]), patch.object(
            worker,
            "generate_market_snapshot",
        ) as generate_snapshot, patch.object(
            worker,
            "dispatch_signal_pushes",
        ) as push_signals, patch.object(
            worker,
            "set_workers",
        ):
            worker.worker_loop(stop_event)

        generate_snapshot.assert_called_once_with([], reuse_last_good_on_empty=True)
        push_signals.assert_not_called()

    def test_snapshot_worker_uses_engine_bootstrap_when_signal_cache_is_empty(self):
        class SingleCycleStopEvent:
            def __init__(self):
                self.wait_calls = 0

            def is_set(self):
                return self.wait_calls > 0

            def wait(self, timeout):
                self.wait_calls += 1
                return True

        original_stop_event = snapshot_worker._stop_event
        snapshot_worker._stop_event = SingleCycleStopEvent()

        try:
            with patch.object(snapshot_worker, "get_all_signals", return_value=[]), patch.object(
                snapshot_worker,
                "generate_market_snapshot",
            ) as generate_snapshot:
                snapshot_worker._snapshot_loop()
        finally:
            snapshot_worker._stop_event = original_stop_event

        generate_snapshot.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
