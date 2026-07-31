import unittest
from unittest.mock import patch

import worker
from app.system import ai_worker
from app.system import chart_warmup
from app.system import news_warmup
from app.system import quote_warmup
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

    def test_news_warmup_skips_repeated_empty_provider_calls_during_cooldown(self):
        original_last_warmup_at = news_warmup._last_warmup_at
        original_cooldowns = dict(news_warmup._symbol_cooldowns)
        try:
            news_warmup._last_warmup_at = 0.0
            news_warmup._symbol_cooldowns.clear()
            with patch.object(news_warmup, "_requested_symbols", return_value=[("PETR4", 6)]), patch.object(
                news_warmup,
                "get_cached_symbol_news",
                return_value=[],
            ), patch.object(
                news_warmup,
                "get_symbol_news",
                return_value=[],
            ) as get_news, patch.object(
                news_warmup,
                "_is_on_cooldown",
                return_value=False,
            ):
                first = news_warmup.warm_news_once(limit=0, max_calls=1)
            self.assertIn("PETR4", news_warmup._symbol_cooldowns)
            with patch.object(news_warmup, "_requested_symbols", return_value=[("PETR4", 6)]), patch.object(
                news_warmup,
                "get_cached_symbol_news",
                return_value=[],
            ), patch.object(
                news_warmup,
                "get_symbol_news",
                return_value=[],
            ) as get_news_second, patch.object(
                news_warmup,
                "_is_on_cooldown",
                return_value=True,
            ):
                second = news_warmup.warm_news_once(limit=1, max_calls=1)
        finally:
            news_warmup._last_warmup_at = original_last_warmup_at
            news_warmup._symbol_cooldowns.clear()
            news_warmup._symbol_cooldowns.update(original_cooldowns)

        self.assertEqual(first["attempted"], 1)
        self.assertEqual(second["attempted"], 0)
        self.assertEqual(get_news.call_count, 1)
        self.assertEqual(get_news_second.call_count, 0)

    def test_quote_warmup_skips_repeated_empty_provider_calls_during_cooldown(self):
        from app.services import symbol_sanitizer
        original_quote_cooldowns = dict(quote_warmup._quote_cooldowns)
        original_symbol_cooldowns = dict(symbol_sanitizer._cooldowns)
        try:
            quote_warmup._quote_cooldowns.clear()
            symbol_sanitizer._cooldowns.clear()
            with patch.object(
                quote_warmup,
                "public_quote_symbols",
                return_value=["PETR4"],
            ), patch.object(
                quote_warmup,
                "get_price_snapshots",
                return_value={},
            ) as get_prices, patch.object(
                quote_warmup.time,
                "time",
                return_value=1000.0,
            ):
                first = quote_warmup.warm_quotes_once(limit=1, chunk_size=1)
            quote_warmup._quote_cooldowns["PETR4"] = 2000.0
            with patch.object(
                quote_warmup,
                "public_quote_symbols",
                return_value=["PETR4"],
            ), patch.object(
                quote_warmup,
                "get_price_snapshots",
                return_value={},
            ), patch.object(
                quote_warmup.time,
                "time",
                return_value=1301.0,
            ):
                second = quote_warmup.warm_quotes_once(limit=1, chunk_size=1)
        finally:
            quote_warmup._quote_cooldowns.clear()
            quote_warmup._quote_cooldowns.update(original_quote_cooldowns)
            symbol_sanitizer._cooldowns.clear()
            symbol_sanitizer._cooldowns.update(original_symbol_cooldowns)

        self.assertEqual(first["resolved"], 0)
        self.assertEqual(second["resolved"], 0)
        self.assertEqual(get_prices.call_count, 1)

    def test_chart_warmup_skips_repeated_empty_provider_calls_during_cooldown(self):
        original_chart_cooldowns = dict(chart_warmup._pair_cooldowns)
        try:
            chart_warmup._pair_cooldowns.clear()
            with patch.object(
                chart_warmup,
                "_requested_pairs",
                return_value=[("PETR4", "1D")],
            ), patch.object(
                chart_warmup,
                "_default_symbols",
                return_value=["PETR4"],
            ), patch.object(
                chart_warmup,
                "get_cached_chart_data",
                return_value=[],
            ), patch.object(
                chart_warmup,
                "_get_chart_data_no_persist",
                return_value=[],
            ) as get_chart, patch.object(
                chart_warmup,
                "_is_on_cooldown",
                return_value=False,
            ):
                first = chart_warmup.warm_charts_once(limit=1, max_calls=1)
            self.assertIn("PETR4:1D", chart_warmup._pair_cooldowns)
            with patch.object(
                chart_warmup,
                "_requested_pairs",
                return_value=[("PETR4", "1D")],
            ), patch.object(
                chart_warmup,
                "_default_symbols",
                return_value=["PETR4"],
            ), patch.object(
                chart_warmup,
                "get_cached_chart_data",
                return_value=[],
            ), patch.object(
                chart_warmup,
                "_get_chart_data_no_persist",
                return_value=[],
            ) as get_chart2, patch.object(
                chart_warmup,
                "_is_on_cooldown",
                return_value=True,
            ):
                second = chart_warmup.warm_charts_once(limit=1, max_calls=1)
        finally:
            chart_warmup._pair_cooldowns.clear()
            chart_warmup._pair_cooldowns.update(original_chart_cooldowns)

        self.assertEqual(first["attempted"], 1)
        self.assertEqual(second["attempted"], 0)
        self.assertEqual(get_chart.call_count, 1)
        self.assertEqual(get_chart2.call_count, 0)


if __name__ == "__main__":
    unittest.main()
