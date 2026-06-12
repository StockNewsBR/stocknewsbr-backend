from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import worker
from app.cache.snapshot_cache import SnapshotCache
from app.api import market_routes, routes_chart
from app.services import public_ai_tools_service, ranking
from app.system import push_dispatcher
from app.telegram import telegram_alert_engine
from app.web import routes_chart as web_chart
from app.web import routes_radar as web_radar
from app.services.snapshot_contract import coerce_data_quality, data_quality_label, data_quality_score


ROOT = Path(__file__).resolve().parents[1]


def _actionable_row(ticker="PETR4", score=88.0):
    return {
        "ticker": ticker,
        "symbol": ticker,
        "score": score,
        "signal": "BUY",
        "trade_action": "BUY",
        "decision_ready": True,
        "decision_state": "BUY_READY",
        "data_quality": "priced",
        "price": 37.5,
        "volume": 1_000_000,
        "market_data_updated_at": "2026-06-11T10:00:00+00:00",
        "snapshot_id": "test-snapshot",
    }


class SingleSnapshotSourceTests(unittest.TestCase):
    def test_public_ai_tools_do_not_derive_parallel_tools_when_snapshot_is_empty(self):
        with patch.object(
            public_ai_tools_service,
            "get_snapshot",
            return_value={"generated_at": "2026-06-11T10:00:00+00:00", "ai_tools": {}},
        ):
            payload = public_ai_tools_service.build_public_ai_tools_payload(["PETR4"])

        self.assertEqual(payload["source"], "snapshot_unavailable")
        self.assertFalse(any(payload["tools"].values()))

    def test_public_ai_tools_use_operational_snapshot_tools(self):
        tools = public_ai_tools_service._empty_tools()
        tools["master_score"] = [
            {
                "ticker": "PETR4",
                "tool": "master_score",
                "score": 88.0,
                "signal": "BUY",
                "price": 37.5,
                "volume": 1_000_000,
                "data_quality": "priced",
            }
        ]

        with patch.object(
            public_ai_tools_service,
            "get_snapshot",
            return_value={"generated_at": "2026-06-11T10:00:00+00:00", "ai_tools": tools},
        ):
            payload = public_ai_tools_service.build_public_ai_tools_payload()

        self.assertEqual(payload["source"], "snapshot")
        self.assertEqual(payload["tools"]["master_score"][0]["ticker"], "PETR4")

    def test_public_ai_tools_service_has_no_quote_or_history_fallback(self):
        text = (ROOT / "app" / "services" / "public_ai_tools_service.py").read_text(encoding="utf-8")

        self.assertNotIn("get_cached_quote_payload", text)
        self.assertNotIn("quote_cache_derived", text)
        self.assertNotIn("get_ai_alert_history_snapshot", text)

    def test_worker_dispatches_pushes_from_generated_snapshot(self):
        class SingleCycleStopEvent:
            def __init__(self):
                self.wait_calls = 0

            def is_set(self):
                return self.wait_calls > 0

            def wait(self, timeout):
                self.wait_calls += 1
                return True

        raw_signal = {"ticker": "RAW", "score": 99.0, "signal": "BUY"}
        snapshot_signal = _actionable_row("PETR4", score=88.0)

        with patch.object(worker, "safe_run_engine", return_value=[raw_signal]), patch.object(
            worker,
            "generate_market_snapshot",
            return_value={"signals": [snapshot_signal], "source": "signal_argument", "stale": False},
        ), patch.object(
            worker,
            "dispatch_signal_pushes",
        ) as push_signals, patch.object(
            worker,
            "set_workers",
        ):
            worker.worker_loop(SingleCycleStopEvent())

        push_signals.assert_called_once_with([snapshot_signal])

    def test_push_dispatch_blocks_invalid_snapshot_rows(self):
        blocked = {
            "ticker": "PETR4",
            "score": 99.0,
            "signal": "BUY",
            "decision_ready": False,
            "decision_state": "DO_NOT_TRADE",
            "data_quality": "score_only",
            "price": 0,
            "volume": 0,
        }
        self.assertEqual(push_dispatcher._eligible_signals([blocked]), [])

    def test_push_dispatch_blocks_not_ready_decision_state(self):
        blocked = {
            **_actionable_row("PETR4", score=99.0),
            "decision_ready": True,
            "decision_state": "NO_TRADE",
        }

        self.assertEqual(push_dispatcher._eligible_signals([blocked]), [])

    def test_telegram_direct_alert_blocks_invalid_snapshot_rows(self):
        blocked = {
            **_actionable_row("PETR4", score=99.0),
            "decision_ready": False,
            "decision_state": "DO_NOT_TRADE",
            "blocked_reasons": ["auditor_blocked"],
        }

        with patch.object(telegram_alert_engine, "format_signal_alert") as format_alert, patch.object(
            telegram_alert_engine,
            "send_alert",
        ) as send_alert:
            telegram_alert_engine.send_signal_alert(blocked)

        format_alert.assert_not_called()
        send_alert.assert_not_called()

    def test_ranking_preserves_snapshot_metadata(self):
        row = _actionable_row("PETR4")

        with patch.object(
            ranking,
            "get_snapshot_info",
            return_value={"signals": 1, "age_seconds": 0, "timestamp": 1, "has_signals": True, "is_empty": False},
        ), patch.object(
            ranking,
            "get_snapshot_signals",
            return_value=[row],
        ):
            payload = ranking.get_ranking(force_refresh=True)

        self.assertEqual(payload[0]["price"], row["price"])
        self.assertEqual(payload[0]["volume"], row["volume"])
        self.assertEqual(payload[0]["data_quality"], "real_time")
        self.assertEqual(payload[0]["market_data_updated_at"], row["market_data_updated_at"])
        self.assertEqual(payload[0]["snapshot_id"], row["snapshot_id"])

    def test_web_radar_preserves_snapshot_metadata(self):
        row = {**_actionable_row("PETR4"), "events": ["momentum"]}

        with patch.object(web_radar, "get_snapshot_signals", return_value=[row]):
            payload = web_radar.get_radar()

        self.assertEqual(payload[0]["price"], row["price"])
        self.assertEqual(payload[0]["volume"], row["volume"])
        self.assertEqual(payload[0]["data_quality"], row["data_quality"])
        self.assertEqual(payload[0]["market_data_updated_at"], row["market_data_updated_at"])
        self.assertEqual(payload[0]["snapshot_id"], row["snapshot_id"])
        self.assertEqual(payload[0]["events"][0]["type"], "momentum")

    def test_legacy_market_radar_excludes_blocked_score_only_rows(self):
        actionable = {
            **_actionable_row("PETR4", score=25.0),
            "signal": "SHORT",
            "trade_action": "SHORT",
            "decision_state": "SHORT_READY",
        }
        blocked = {
            **_actionable_row("BLOQ1", score=5.0),
            "signal": "SHORT",
            "trade_action": "SHORT",
            "decision_ready": False,
            "decision_state": "DO_NOT_TRADE",
            "data_quality": "score_only",
            "price": 0,
            "volume": 0,
            "blocked_reasons": ["price_missing_or_zero"],
        }

        with patch.object(market_routes, "get_snapshot_signals", return_value=[blocked, actionable]):
            payload = market_routes.get_market_radar(current_user=SimpleNamespace(plan="premium"))

        self.assertEqual([row["ticker"] for row in payload["bearish"]], ["PETR4"])

    def test_chart_routes_preserve_snapshot_metadata_in_overlay_signals(self):
        row = {**_actionable_row("PETR4"), "events": ["momentum"]}
        ohlc = [{"time": "2026-06-11T10:00:00+00:00", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 1000}]

        with patch.object(routes_chart, "get_cached_chart_data", return_value=ohlc), patch.object(
            routes_chart,
            "load_chart_data_cache_first",
            return_value=ohlc,
        ), patch.object(
            routes_chart,
            "get_snapshot_signals",
            return_value=[row],
        ), patch.object(
            routes_chart,
            "build_chart_signal_payload",
            return_value={},
        ):
            app_payload = routes_chart.chart("PETR4", current_user=SimpleNamespace(plan="premium"))

        with patch.object(web_chart, "get_cached_chart_data", return_value=ohlc), patch.object(
            web_chart,
            "load_chart_data_cache_first",
            return_value=ohlc,
        ), patch.object(
            web_chart,
            "get_snapshot_signals",
            return_value=[row],
        ), patch.object(
            web_chart,
            "build_chart_signal_payload",
            return_value={},
        ):
            web_payload = web_chart.get_chart("PETR4")

        for payload in (app_payload, web_payload):
            signal = payload["signals"][0]
            self.assertEqual(signal["price"], row["price"])
            self.assertEqual(signal["volume"], row["volume"])
            self.assertEqual(signal["data_quality"], row["data_quality"])
            self.assertEqual(signal["market_data_updated_at"], row["market_data_updated_at"])
            self.assertEqual(signal["snapshot_id"], row["snapshot_id"])
            self.assertEqual(signal["events"][0]["type"], "momentum")

    def test_push_payload_carries_snapshot_metadata(self):
        class Query:
            def filter(self, *args, **kwargs):
                return self

            def all(self):
                return [SimpleNamespace(id=7)]

        class FakeDb:
            def query(self, _model):
                return Query()

            def close(self):
                return None

        row = _actionable_row("PETR4")

        with patch.object(push_dispatcher, "get_push_token_store", return_value={"7": ["token"]}), patch.object(
            push_dispatcher,
            "SessionLocal",
            return_value=FakeDb(),
        ), patch.object(
            push_dispatcher,
            "_load_state",
            return_value={},
        ), patch.object(
            push_dispatcher,
            "_save_state",
        ), patch.object(
            push_dispatcher,
            "send_push_notification",
            return_value={"sent": 1},
        ) as send_push:
            result = push_dispatcher.dispatch_signal_pushes([row])

        self.assertEqual(result["sent"], 1)
        data = send_push.call_args.kwargs["data"]
        self.assertEqual(data["price"], str(row["price"]))
        self.assertEqual(data["volume"], str(row["volume"]))
        self.assertEqual(data["data_quality"], row["data_quality"])
        self.assertEqual(data["decision_state"], row["decision_state"])
        self.assertEqual(data["trade_action"], row["trade_action"])
        self.assertEqual(data["market_data_updated_at"], row["market_data_updated_at"])
        self.assertEqual(data["snapshot_id"], row["snapshot_id"])

    def test_data_quality_contract_normalizes_quality_and_labels(self):
        self.assertEqual(coerce_data_quality({"data_quality": "priced", "source": "snapshot"}), "cached")
        self.assertEqual(coerce_data_quality({"data_quality": "score_only"}), "score_only")
        self.assertEqual(coerce_data_quality({"data_quality": "stale", "stale": True}), "stale")
        self.assertEqual(coerce_data_quality({"data_quality": "empty"}), "empty")
        self.assertEqual(coerce_data_quality({"provider_error": "timeout"}), "invalid")
        self.assertEqual(data_quality_label("cached"), "Dados Confiáveis")
        self.assertEqual(data_quality_label("score_only"), "Dados Parciais")
        self.assertEqual(data_quality_label("stale"), "Dados Limitados")
        self.assertGreater(data_quality_score("cached"), data_quality_score("score_only"))
        self.assertGreater(data_quality_score("score_only"), data_quality_score("stale"))

    def test_snapshot_cache_preserves_good_payload_when_empty_update_arrives(self):
        cache = SnapshotCache()
        cache.update({"signals": [_actionable_row("PETR4")]})
        first = cache.get()
        cache.update({"signals": [], "source": "empty", "stale": True})
        second = cache.get()

        self.assertTrue(first["signals"])
        self.assertEqual(second["signals"][0]["ticker"], "PETR4")

    def test_snapshot_cache_stats_count_only_actionable_bullish_bearish(self):
        cache = SnapshotCache()
        cache.update(
            {
                "signals": [
                    _actionable_row("PETR4", score=88.0),
                    {
                        "ticker": "BLOCKED",
                        "symbol": "BLOCKED",
                        "score": 99.0,
                        "signal": "BUY",
                        "trade_action": "BUY",
                        "decision_ready": False,
                        "decision_state": "DO_NOT_TRADE",
                        "data_quality": "score_only",
                        "price": 0,
                        "volume": 0,
                        "blocked_reasons": ["price_missing_or_zero"],
                    },
                    {
                        "ticker": "WATCH1",
                        "symbol": "WATCH1",
                        "score": 92.0,
                        "signal": "WATCH_BUY",
                        "trade_action": "WATCH_BUY",
                        "decision_ready": False,
                        "decision_state": "WATCH",
                        "data_quality": "priced",
                        "price": 10,
                        "volume": 1000,
                    },
                ]
            }
        )

        stats = cache.get()["stats"]
        self.assertEqual(stats["bullish"], 1)
        self.assertEqual(stats["actionable_bullish"], 1)
        self.assertEqual(stats["bullish_candidates"], 3)
        self.assertEqual(stats["blocked_signals"], 1)
        self.assertEqual(stats["watchlist_candidates"], 1)


if __name__ == "__main__":
    unittest.main()
