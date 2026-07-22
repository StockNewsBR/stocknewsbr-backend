import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_public_market
from app.api import routes_public_market_live
from app.market import market_data_loader
from app.services import public_market_data_service
from app.services import quote_service
from app.system import quote_warmup
from app.services.quote_service import classify_quote_payload, empty_quote_payload, is_usable_quote_payload


class PublicMarketRouteTests(unittest.TestCase):
    def test_bundle_http_publishes_top_level_metrics_without_erasing_insight(self):
        app = FastAPI()
        app.include_router(routes_public_market_live.router)
        for symbol in ("AAPL", "AAL", "PETR4", "ITUB4", "ASAI3"):
            quote = {"symbol": symbol, "provider_symbol": f"{symbol}.SA", "price": 42.4, "volume": 704, "average_volume": 930, "quote_time": "2026-07-21T12:00:00Z"}
            insight = {"symbol": symbol, "rsi": 61.0, "trend_bias": "alta", "master_score": 7.1, "strategic_panel": {"symbol": symbol}}
            chart = {"ticker": symbol, "ohlc": [], "zones": [], "summary": {"as_of": "2026-07-21T12:00:00Z"}}
            with patch.object(routes_public_market_live, "request_symbol_hydration"), patch.object(
                routes_public_market_live, "cached_price_payloads", return_value={symbol: quote}
            ), patch.object(routes_public_market_live, "_resolve_cached_quote", return_value=quote), patch.object(
                routes_public_market_live, "public_market_insight", return_value=insight
            ), patch.object(routes_public_market_live, "public_market_chart", return_value=chart), patch.object(
                routes_public_market_live, "build_public_news_payload", return_value={"items": [], "data_status": "READY"}
            ), patch.object(routes_public_market_live, "build_public_ai_tools_payload", return_value={"tools": {}, "status": "PENDING"}), patch.object(
                routes_public_market_live, "get_symbol_analysis", return_value={}
            ), patch.object(
                routes_public_market_live, "_load_chart_data_fast",
                return_value=[{"time": f"2026-07-{index + 1:02d}T12:00:00Z", "close": 30 + index} for index in range(15)],
            ), patch.object(routes_public_market_live, "hydration_status", return_value={}):
                payload = TestClient(app).get(f"/public/market/bundle/{symbol}?interval=1D&limit=6&locale=pt-BR").json()

            self.assertEqual(payload["market_metrics"]["canonical_symbol"], symbol)
            self.assertEqual(payload["market_metrics"]["timeframe"], "1D")
            self.assertIn("operational_view", payload["market_metrics"])
            self.assertEqual(payload["market_metrics"]["sentiment"]["status"], "INSUFFICIENT_DATA")
            self.assertEqual(payload["market_metrics"]["volume_vs_daily_average"]["status"], "READY")
            self.assertEqual(payload["market_metrics"]["intraday_rvol"]["status"], "INSUFFICIENT_DATA")
            self.assertIsNone(payload["market_metrics"]["intraday_rvol"]["rvol_ratio"])
            self.assertEqual(payload["market_metrics"]["operational_view"]["operational_context"]["master_score"]["status"], "PARTIAL")
            self.assertIn("rsi", payload["insight"])
            self.assertEqual(payload["insight"]["trend_bias"], "alta")
            self.assertIn("strategic_panel", payload["insight"])

    def test_bundle_keeps_daily_trend_distinct_from_intraday_direction(self):
        app = FastAPI()
        app.include_router(routes_public_market_live.router)
        quote = {"symbol": "PETR4", "price": 42.4, "volume": 704, "average_volume": 930, "quote_time": "2026-07-21T12:00:00Z"}
        daily = [{"time": f"2026-07-{index + 1:02d}T12:00:00Z", "close": 30 + index} for index in range(15)]
        insight = {"symbol": "PETR4", "rsi": 61.0, "rsi_metadata": {"status": "AVAILABLE", "as_of": daily[-1]["time"], "source": "canonical_indicator_engine"}}
        chart = {"ticker": "PETR4", "ohlc": [], "zones": [], "rsi_metadata": {"timeframe": "5m"}, "summary": {"trend_bias": "baixa", "as_of": "2026-07-21T12:00:00Z"}}
        with patch.object(routes_public_market_live, "request_symbol_hydration"), patch.object(
            routes_public_market_live, "cached_price_payloads", return_value={"PETR4": quote}
        ), patch.object(routes_public_market_live, "_resolve_cached_quote", return_value=quote), patch.object(
            routes_public_market_live, "public_market_insight", return_value=insight
        ), patch.object(routes_public_market_live, "public_market_chart", return_value=chart), patch.object(
            routes_public_market_live, "_load_chart_data_fast", return_value=daily
        ), patch.object(routes_public_market_live, "build_public_news_payload", return_value={"items": [], "data_status": "READY"}), patch.object(
            routes_public_market_live, "build_public_ai_tools_payload", return_value={"tools": {}, "status": "PENDING"}
        ), patch.object(routes_public_market_live, "get_symbol_analysis", return_value={}), patch.object(
            routes_public_market_live, "hydration_status", return_value={}):
            payload = TestClient(app).get("/public/market/bundle/PETR4?interval=1D&limit=6&locale=pt-BR").json()

        context = payload["market_metrics"]["operational_view"]["technical_context"]
        self.assertEqual(context["trend_d1"]["value"], "alta")
        self.assertEqual(context["trend_d1"]["timeframe"], "1d")
        self.assertEqual(context["intraday_direction_5m"]["value"], "baixa")
        self.assertEqual(context["intraday_direction_5m"]["timeframe"], "5m")

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

    def test_empty_quote_payload_exposes_missing_fields_contract(self):
        payload = empty_quote_payload("BNY")

        self.assertFalse(payload["core_data"])
        self.assertFalse(payload["strategic_core_data"])
        self.assertEqual(payload["missing_fields"], ["price", "volume", "score", "rsi", "bias"])
        self.assertEqual(payload["quote_missing_fields"], ["price", "volume"])
        self.assertFalse(payload["field_status"]["quote"])

    def test_on_demand_quote_skips_empty_alias_before_valid_provider_symbol(self):
        with patch.object(quote_service, "get_cached_quote_payload", return_value=None), patch.object(
            quote_service,
            "get_price_snapshot",
            side_effect=[
                None,
                {
                    "symbol": "AXIA7.SA",
                    "price": 55.78,
                    "change": 0.0,
                    "change_pct": 0.0,
                    "volume": 91863885,
                    "source": "market_cache",
                },
            ],
        ):
            payload = quote_service.get_quote_payload("AXIA7", allow_fetch=True)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["symbol"], "AXIA7")
        self.assertEqual(payload["price"], 55.78)
        self.assertTrue(payload["core_data"])

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
        ) as build_payload:
            payload = routes_public_market.public_news("AAPL", limit=3)

        self.assertEqual(payload["symbol"], "AAPL")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["source"], "public")
        build_payload.assert_called_once_with("AAPL", limit=3, source="public", allow_fetch=False, schedule_warmup=True)

    def test_public_ai_tools_returns_visible_history_contract(self):
        with patch.object(
            routes_public_market,
            "build_public_ai_tools_payload",
            return_value={
                "reset_key": "2026-05-18",
                "max_rows_per_tool": 20,
                "tools": {"flow": [{"ticker": "F", "detected_at": "2026-05-18T12:30:00+00:00"}]},
            },
        ):
            payload = routes_public_market.public_ai_tools()

        self.assertEqual(payload["reset_key"], "2026-05-18")
        self.assertEqual(payload["max_rows_per_tool"], 20)
        self.assertEqual(payload["tools"]["flow"][0]["ticker"], "F")

    def test_public_bundle_uses_cached_snapshot_payloads(self):
        with patch.object(routes_public_market_live, "request_symbol_hydration"), patch.object(
            routes_public_market_live, "get_symbol_analysis", return_value={}
        ), patch.object(
            routes_public_market_live, "hydration_status", return_value={}
        ), patch.object(
            routes_public_market_live,
            "cached_price_payloads",
            return_value={"F": {"symbol": "F", "price": 14.9, "volume": 1_000_000, "source": "snapshot"}},
        ), patch.object(
            routes_public_market_live,
            "public_market_insight",
            return_value={"symbol": "F", "score": 6.2},
        ), patch.object(
            routes_public_market_live,
            "public_market_chart",
            return_value={"ticker": "F", "ohlc": [{"close": 14.9}], "series": [], "markers": [], "zones": [], "summary": {}},
        ), patch.object(
            routes_public_market_live,
            "build_public_news_payload",
            return_value={"symbol": "F", "items": [], "count": 0},
        ), patch.object(
            routes_public_market_live,
            "build_public_ai_tools_payload",
            return_value={"tools": {"risk": []}, "source": "snapshot"},
        ):
            payload = routes_public_market_live.public_market_bundle("F", interval="1D")

        self.assertEqual(payload["symbol"], "F")
        self.assertEqual(payload["quote"]["price"], 14.9)
        self.assertEqual(payload["insight"]["score"], 6.2)
        self.assertEqual(payload["source"], "cache_snapshot_bundle")

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
        self.assertEqual(payload["interval"], "1D")
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
        with patch.object(routes_public_market_live, "get_cached_quote_payload", return_value=None):
            payload = routes_public_market_live._resolve_cached_quote(
                {"F": {"symbol": "F", "volume": 1000, "change": 0.12, "source": "market_cache"}},
                "F",
            )

        self.assertEqual(payload["symbol"], "F")
        self.assertEqual(payload["source"], "empty")
        self.assertIsNone(payload["price"])

    def test_public_bundle_quote_uses_valid_alias_payload_when_key_differs(self):
        payload = routes_public_market_live._resolve_cached_quote(
            {"SNAPSHOT:B3SA3": {"symbol": "B3SA3.SA", "price": 15.23, "volume": 2_056_800, "source": "snapshot"}},
            "B3SA3",
        )

        self.assertEqual(payload["symbol"], "B3SA3")
        self.assertEqual(payload["price"], 15.23)
        self.assertEqual(payload["source"], "snapshot")

    def test_live_batch_quote_rejects_cross_symbol_cache_payload(self):
        with patch.object(
            routes_public_market_live,
            "cached_price_payloads",
            return_value={
                "ASAI3": {
                    "symbol": "PETR4",
                    "requested_symbol": "PETR4",
                    "canonical_symbol": "PETR4",
                    "provider_symbol": "PETR4.SA",
                    "display_symbol": "PETR4",
                    "asset_type": "B3",
                    "market": "B3",
                    "currency": "BRL",
                    "timezone": "America/Sao_Paulo",
                    "identity_preserved": True,
                    "price_semantics": "direct_market_price",
                    "freshness_semantics": "provider_observation_or_cache_ttl",
                    "price": 38.8,
                    "volume": 12_000_000,
                    "source": "market_cache",
                },
                "PETR4": {
                    "symbol": "PETR4",
                    "requested_symbol": "PETR4",
                    "canonical_symbol": "PETR4",
                    "provider_symbol": "PETR4.SA",
                    "display_symbol": "PETR4",
                    "asset_type": "B3",
                    "market": "B3",
                    "currency": "BRL",
                    "timezone": "America/Sao_Paulo",
                    "identity_preserved": True,
                    "price_semantics": "direct_market_price",
                    "freshness_semantics": "provider_observation_or_cache_ttl",
                    "price": 38.8,
                    "volume": 12_000_000,
                    "source": "market_cache",
                },
            },
        ), patch.object(routes_public_market_live, "get_cached_quote_payload", return_value=None):
            payload = routes_public_market_live.public_quotes("ASAI3,PETR4")

        self.assertEqual(payload["items"][0]["symbol"], "ASAI3")
        self.assertEqual(payload["items"][0]["source"], "empty")
        self.assertIsNone(payload["items"][0]["price"])
        self.assertEqual(payload["items"][1]["symbol"], "PETR4")
        self.assertEqual(payload["items"][1]["price"], 38.8)

    def test_public_bundle_quote_falls_back_to_shared_quote_snapshot(self):
        with patch.object(
            routes_public_market_live,
            "get_cached_quote_payload",
            return_value={"symbol": "B3SA3", "price": 15.23, "volume": 2_056_800, "source": "snapshot"},
        ):
            payload = routes_public_market_live._resolve_cached_quote({}, "B3SA3")

        self.assertEqual(payload["symbol"], "B3SA3")
        self.assertEqual(payload["price"], 15.23)
        self.assertEqual(payload["source"], "snapshot")

    def test_live_batch_quote_does_not_request_background_warmup_for_empty_symbols(self):
        with patch.object(routes_public_market_live, "cached_price_payloads", return_value={}), patch.object(
            routes_public_market_live,
            "get_cached_quote_payload",
            return_value=None,
        ):
            payload = routes_public_market_live.public_quotes("BA")

        self.assertEqual(payload["items"][0]["symbol"], "BA")
        self.assertEqual(payload["items"][0]["source"], "empty")
        self.assertFalse(payload["items"][0]["core_data"])
        self.assertIn("price", payload["items"][0]["missing_fields"])

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

    def test_public_bundle_does_not_request_quote_warmup_when_cache_is_empty(self):
        with patch.object(routes_public_market_live, "cached_price_payloads", return_value={}), patch.object(
            routes_public_market_live,
            "get_cached_quote_payload",
            return_value=None,
        ), patch.object(
            routes_public_market_live,
            "public_market_insight",
            return_value={"symbol": "BA", "status": "empty"},
        ), patch.object(
            routes_public_market_live,
            "public_market_chart",
            return_value={"ticker": "BA", "ohlc": [], "series": [], "markers": [], "zones": [], "summary": {}},
        ), patch.object(
            routes_public_market_live,
            "build_public_news_payload",
            return_value={"symbol": "BA", "items": [], "count": 0},
        ), patch.object(
            routes_public_market_live,
            "build_public_ai_tools_payload",
            return_value={"tools": {}, "source": "snapshot"},
        ):
            payload = routes_public_market_live.public_market_bundle("BA", interval="1D")

        self.assertEqual(payload["symbol"], "BA")
        self.assertEqual(payload["quote"]["source"], "empty")

    def test_public_chart_blocks_synthetic_quote_fallback_for_b3_futures(self):
        with patch.object(routes_public_market_live, "load_public_chart_rows", return_value=[]), patch.object(
            routes_public_market_live,
            "_build_quote_fallback_chart",
            return_value=[{"time": 1, "close": 176000, "source": "quote_cache_fallback"}],
        ) as fallback:
            payload = routes_public_market_live.public_market_chart("WINK26", range_value="1D")

        fallback.assert_not_called()
        self.assertEqual(payload["ticker"], "WINK26")
        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["ohlc"], [])
        self.assertEqual(payload["summary"]["provider_status"], "b3_future_exact_chart_unavailable")

    def test_public_chart_blocks_synthetic_quote_fallback_for_equities(self):
        with patch.object(routes_public_market_live, "load_public_chart_rows", return_value=[]), patch.object(
            routes_public_market_live,
            "_build_quote_fallback_chart",
            return_value=[{"time": 1, "close": 14.9, "source": "quote_cache_fallback"}],
        ) as fallback:
            payload = routes_public_market_live.public_market_chart("F", range_value="1D")

        fallback.assert_not_called()
        self.assertEqual(payload["ticker"], "F")
        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["ohlc"], [])
        self.assertEqual(payload["summary"]["provider_status"], "empty_chart")

    def test_public_indices_returns_six_indices_in_contract_shape(self):
        closes = [{"close": float(i), "time": f"2026-07-{i:02d}T00:00:00"} for i in range(1, 71)]
        with patch.object(
            public_market_data_service,
            "cached_price_payloads",
            return_value={"^BVSP": {"symbol": "^BVSP", "price": 173714.08, "change": -111.19, "change_pct": -0.06}},
        ), patch.object(
            public_market_data_service, "load_public_chart_rows", return_value=closes
        ):
            payload = routes_public_market_live.public_market_indices()

        self.assertEqual(
            [item["symbol"] for item in payload["items"]],
            ["IBOV", "SP500", "NASDAQ", "DOW", "RUSSELL", "USDBRL"],
        )
        ibov = payload["items"][0]
        self.assertEqual(ibov["display_name"], "Ibovespa")
        self.assertEqual(ibov["price"], 173714.08)
        self.assertEqual(ibov["change"], -111.19)
        self.assertEqual(ibov["change_pct"], -0.06)
        self.assertEqual(ibov["currency"], "BRL")
        self.assertEqual(ibov["status"], "valid")
        # <= 60 recent closes, oldest first
        self.assertEqual(len(ibov["spark"]), 60)
        self.assertEqual(ibov["spark"][0], 11.0)
        self.assertEqual(ibov["spark"][-1], 70.0)
        # USDBRL is last; Russell 2000 sits at index 4 and is a USD index.
        self.assertEqual(payload["items"][4]["currency"], "USD")
        self.assertEqual(payload["items"][-1]["currency"], "BRL")

    def test_public_quote_cache_miss_enqueues_warmup_without_inline_provider_call(self):
        with quote_warmup._lock:
            quote_warmup._ondemand_last_at.clear()
            quote_warmup._ondemand_recent.clear()

        with patch.object(quote_warmup, "_is_quote_on_cooldown", return_value=False), patch.object(
            quote_warmup, "request_quote_warmup"
        ) as enqueue, patch.object(
            market_data_loader, "get_price_snapshots"
        ) as provider, patch.object(
            routes_public_market_live, "cached_price_payloads", return_value={}
        ), patch.object(
            routes_public_market_live, "get_cached_quote_payload", return_value=None
        ):
            payload = routes_public_market_live.public_quotes(symbols="ADP")

            enqueue.assert_called_once_with("ADP")
            provider.assert_not_called()

            # A typing user must not hammer the provider: the repeat is suppressed.
            routes_public_market_live.public_quotes(symbols="ADP")
            self.assertEqual(enqueue.call_count, 1)

        self.assertEqual(payload["items"][0]["symbol"], "ADP")
        self.assertIsNone(payload["items"][0]["price"])

    def test_public_insight_empty_is_explicit_not_silent_summary(self):
        with patch.object(routes_public_market_live, "_load_chart_data_fast", return_value=[]):
            payload = routes_public_market_live.public_market_insight("F", interval="1D")

        self.assertEqual(payload["symbol"], "F")
        self.assertEqual(payload["status"], "empty")
        self.assertTrue(payload["fallback"])
        self.assertEqual(payload["summary"]["provider_status"], "empty_chart")


if __name__ == "__main__":
    unittest.main()
