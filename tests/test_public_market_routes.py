import unittest
from unittest.mock import patch

from app.api import routes_public_market
from app.api import routes_public_market_live
from app.services.quote_service import classify_quote_payload, is_usable_quote_payload


class PublicMarketRouteTests(unittest.TestCase):
    def test_public_aliases_include_futures_provider_symbols(self):
        self.assertIn("NQ=F", routes_public_market_live._symbol_aliases("NQ"))
        self.assertIn("MNQ=F", routes_public_market_live._symbol_aliases("MNO"))
        self.assertIn("ES=F", routes_public_market_live._symbol_aliases("ES"))
        self.assertIn("WINM26.SA", routes_public_market_live._symbol_aliases("WINM26"))
        self.assertIn("WDOM26.SA", routes_public_market_live._symbol_aliases("WDOM26"))

    def test_public_quote_prefers_snapshot_cache(self):
        with patch.object(
            routes_public_market,
            "get_cached_quote_payload",
            return_value={"symbol": "PETR4", "price": 47.12, "change": 0.22, "change_pct": 0.47, "volume": 1234, "high": 48, "low": 46, "source": "snapshot"},
        ):
            payload = routes_public_market.public_quote("petR4")

        self.assertEqual(payload["symbol"], "PETR4")
        self.assertEqual(payload["source"], "snapshot")
        self.assertEqual(payload["price"], 47.12)

    def test_public_quote_returns_empty_when_cache_is_cold(self):
        with patch.object(
            routes_public_market,
            "get_cached_quote_payload",
            return_value=None,
        ), patch.object(
            routes_public_market,
            "empty_quote_payload",
            return_value={"symbol": "AAPL", "price": None, "source": "empty"},
        ):
            payload = routes_public_market.public_quote("AAPL")

        self.assertEqual(payload["symbol"], "AAPL")
        self.assertEqual(payload["source"], "empty")
        self.assertIsNone(payload["price"])

    def test_public_quote_rejects_partial_cache_without_price(self):
        with patch.object(
            routes_public_market,
            "get_cached_quote_payload",
            return_value={"symbol": "F", "change": 0.12, "change_pct": 1.1, "volume": 1234, "source": "snapshot"},
        ), patch.object(
            routes_public_market,
            "empty_quote_payload",
            return_value={"symbol": "F", "price": None, "source": "empty"},
        ):
            payload = routes_public_market.public_quote("F")

        self.assertEqual(payload["symbol"], "F")
        self.assertEqual(payload["source"], "empty")
        self.assertIsNone(payload["price"])

    def test_public_news_returns_service_payload(self):
        with patch.object(
            routes_public_market,
            "build_public_news_payload",
            return_value={
                "symbol": "AAPL",
                "items": [{"id": "1"}],
                "count": 1,
                "report": {"status": "ok"},
                "cache": {"status": "warm"},
                "source": "public",
            },
        ):
            payload = routes_public_market.public_news("AAPL", limit=3)

        self.assertEqual(payload["symbol"], "AAPL")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["source"], "public")

    def test_public_ai_tools_returns_visible_history_contract(self):
        with patch.object(
            routes_public_market,
            "get_ai_alert_history_snapshot",
            return_value={
                "reset_key": "2026-05-18",
                "max_rows_per_tool": 20,
                "tools": {"heat_map": [{"ticker": "F", "detected_at": "2026-05-18T12:30:00+00:00"}]},
            },
        ):
            payload = routes_public_market.public_ai_tools()

        self.assertEqual(payload["reset_key"], "2026-05-18")
        self.assertEqual(payload["max_rows_per_tool"], 20)
        self.assertEqual(payload["tools"]["heat_map"][0]["ticker"], "F")

    def test_public_chart_returns_overlay_payload(self):
        ohlc = [{"time": 1, "close": 10.0, "high": 11.0, "low": 9.5}]
        with patch.object(
            routes_public_market_live,
            "load_public_chart_rows",
            return_value=ohlc,
        ), patch.object(
            routes_public_market_live,
            "build_chart_signal_payload",
            return_value={"signal": "WATCH_LONG", "summary": {"trend_bias": "alta"}},
        ), patch.object(
            routes_public_market_live,
            "build_chart_overlays",
            return_value={
                "series": ohlc,
                "markers": [{"time": 1}],
                "zones": [{"label": "suporte", "price": 9.5}],
                "summary": {"ticker": "PETR4", "trend_bias": "alta"},
            },
        ):
            payload = routes_public_market_live.public_market_chart("petr4")

        self.assertEqual(payload["ticker"], "PETR4")
        self.assertEqual(payload["summary"]["trend_bias"], "alta")
        self.assertEqual(payload["series"][0]["close"], 10.0)

    def test_live_quote_validation_rejects_volume_only_payload(self):
        self.assertFalse(routes_public_market_live._has_usable_quote_payload({"symbol": "F", "volume": 1000, "change": 0.12}))
        self.assertFalse(routes_public_market_live._has_usable_quote_payload({"symbol": "F", "price": 0, "volume": 1000}))
        self.assertTrue(routes_public_market_live._has_usable_quote_payload({"symbol": "F", "price": 12.34, "volume": 1000}))
        self.assertEqual(classify_quote_payload({"symbol": "F", "volume": 1000, "change": 0.12}), "partial")
        self.assertEqual(classify_quote_payload({"symbol": "F", "price": None, "source": "empty"}), "empty")
        self.assertEqual(classify_quote_payload({"symbol": "F", "price": 12.34, "stale": True}), "stale")
        self.assertEqual(classify_quote_payload({"symbol": "WINM26", "price": 179000, "source": "reference_proxy"}), "reference")
        self.assertTrue(is_usable_quote_payload({"symbol": "F", "price": 12.34, "stale": True}))
        self.assertTrue(is_usable_quote_payload({"symbol": "WINM26", "price": 179000, "source": "reference_proxy"}))

    def test_live_batch_quote_does_not_return_partial_cache_as_valid(self):
        payload = routes_public_market_live._resolve_cached_quote(
            {"F": {"symbol": "F", "volume": 1000, "change": 0.12, "source": "market_cache"}},
            "F",
        )

        self.assertEqual(payload["symbol"], "F")
        self.assertEqual(payload["source"], "empty")
        self.assertIsNone(payload["price"])

    def test_public_chart_accepts_range_query_alias(self):
        ohlc = [{"time": 1, "open": 9.8, "close": 10.0, "high": 11.0, "low": 9.5}]
        captured = {}

        def fake_load_chart(_ticker, interval):
            captured["interval"] = interval
            return ohlc

        with patch.object(
            routes_public_market_live,
            "_load_chart_data_fast",
            side_effect=fake_load_chart,
        ), patch.object(
            routes_public_market_live,
            "build_chart_signal_payload",
            return_value={"signal": "WATCH_LONG", "summary": {"trend_bias": "alta"}},
        ), patch.object(
            routes_public_market_live,
            "build_chart_overlays",
            return_value={
                "series": ohlc,
                "markers": [],
                "zones": [],
                "summary": {"ticker": "F", "trend_bias": "alta"},
            },
        ):
            payload = routes_public_market_live.public_market_chart("F", range_value="3M")

        self.assertEqual(captured["interval"], "3M")
        self.assertEqual(payload["interval"], "3M")
        self.assertEqual(payload["ticker"], "F")

    def test_public_chart_empty_is_explicit_not_silent_object(self):
        with patch.object(routes_public_market_live, "_load_chart_data_fast", return_value=[]):
            payload = routes_public_market_live.public_market_chart("F", range_value="1D")

        self.assertEqual(payload["ticker"], "F")
        self.assertEqual(payload["status"], "empty")
        self.assertTrue(payload["fallback"])
        self.assertEqual(payload["ohlc"], [])
        self.assertEqual(payload["summary"]["provider_status"], "empty_chart")

    def test_public_insight_empty_is_explicit_not_silent_summary(self):
        with patch.object(routes_public_market_live, "_load_chart_data_fast", return_value=[]):
            payload = routes_public_market_live.public_market_insight("F", interval="1D")

        self.assertEqual(payload["symbol"], "F")
        self.assertEqual(payload["status"], "empty")
        self.assertTrue(payload["fallback"])
        self.assertEqual(payload["summary"]["provider_status"], "empty_chart")


if __name__ == "__main__":
    unittest.main()
