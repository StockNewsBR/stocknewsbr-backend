import unittest
from unittest.mock import patch

from app.api import routes_public_market_live
from app.services import public_ai_tools_service
from app.services.news_service import NEWS_CACHE_TTL_SECONDS
from app.services.public_market_data_service import normalize_public_chart_zones
from app.system import chart_warmup, news_warmup, symbol_hydration


class OnDemandHydrationTests(unittest.TestCase):
    def test_stale_news_cache_is_refetched_by_request_worker(self):
        with patch.object(news_warmup, "get_cached_symbol_news", return_value=[{"ticker": "ASAI3"}]), patch.object(
            news_warmup, "get_news_cache_info", return_value={"age_seconds": NEWS_CACHE_TTL_SECONDS}
        ), patch.object(news_warmup, "get_symbol_news", return_value=[{"ticker": "ASAI3"}]) as fetch, patch.object(
            news_warmup, "_drop_warmed_requests"
        ):
            news_warmup._warm_single_request("ASAI3", 6, "pt-BR", "ASAI3:6:pt-BR")

        fetch.assert_called_once_with("ASAI3", limit=6, locale="pt-BR")

    def test_chart_request_worker_fetches_a_cache_miss(self):
        with patch.object(chart_warmup, "get_cached_chart_data", return_value=[]), patch.object(
            chart_warmup, "get_chart_data", return_value=[{"close": 10.0}]
        ) as fetch, patch.object(chart_warmup, "_drop_warmed_requests"), patch.object(
            chart_warmup, "record_worker_stage_duration"
        ):
            chart_warmup._warm_single_request("EQTL3", "3M", "EQTL3:3M")

        fetch.assert_called_once_with("EQTL3", "3M")

    def test_bundle_enqueues_hydration_without_provider_work_in_route(self):
        with patch.object(routes_public_market_live, "request_symbol_hydration") as hydrate, patch.object(
            routes_public_market_live, "hydration_status", return_value={"quote": "PENDING", "chart_intraday": "PENDING", "chart_daily": "PENDING", "rsi": "PENDING", "news": "REFRESHING", "ai": "PENDING"}
        ), patch.object(routes_public_market_live, "cached_price_payloads", return_value={}), patch.object(
            routes_public_market_live, "public_market_insight", return_value={"symbol": "AMER3"}
        ), patch.object(routes_public_market_live, "public_market_chart", return_value={"ticker": "AMER3", "ohlc": []}), patch.object(
            routes_public_market_live, "build_public_news_payload", return_value={"symbol": "AMER3", "items": []}
        ), patch.object(routes_public_market_live, "build_public_ai_tools_payload", return_value={"tools": {}}), patch.object(
            routes_public_market_live, "get_symbol_analysis", return_value={}):
            payload = routes_public_market_live.public_market_bundle("AMER3")

        hydrate.assert_called_once_with("AMER3", timeframe="1D", locale="pt-BR", news_limit=6)
        self.assertEqual(payload["data_status"]["rsi"], "PENDING")
        self.assertEqual(payload["hydration"]["status"], "PENDING")
        self.assertEqual(payload["retry_after_seconds"], 3)

    def test_ready_on_demand_analysis_beats_missing_snapshot_symbol(self):
        row = {"ticker": "EQTL3", "symbol": "EQTL3", "price": 10.0, "volume": 1000, "can_trade": False, "data_quality": "priced"}
        with patch("app.system.symbol_hydration.request_symbol_hydration"), patch(
            "app.system.symbol_hydration.get_symbol_analysis",
            return_value={"status": "READY", "updated_at": "2026-07-21T10:00:00+00:00", "ai_tools": {"trend": [row]}},
        ):
            payload = public_ai_tools_service.build_public_ai_tools_payload(symbol="EQTL3", tool="trend", timeframe="1D")

        self.assertEqual(payload["source"], "on_demand")
        self.assertEqual(payload["status"], "READY")

    def test_old_global_snapshot_is_historical_not_an_active_finding(self):
        row = {
            "ticker": "AAPL", "symbol": "AAPL", "price": 200.0, "volume": 1000,
            "data_quality": "real_time", "updated_at": "2026-07-17T12:00:00+00:00",
        }
        snapshot = {
            "generated_at": "2026-07-17T12:00:00+00:00",
            "ai_tools": {"trend": [row]},
        }
        with patch.object(public_ai_tools_service, "get_snapshot", return_value=snapshot):
            payload = public_ai_tools_service.build_public_ai_tools_payload(tool="trend")

        self.assertEqual(payload["status"], "HISTORICAL")
        self.assertEqual(payload["tools"]["trend"], [])
        self.assertEqual(payload["historical_tools"]["trend"][0]["freshness_status"], "HISTORICAL")

    def test_micro_range_is_not_published_as_operational_levels(self):
        rows = [{"time": f"2026-07-21T10:{index:02d}:00Z", "open": 42.4, "high": 42.9, "low": 41.9, "close": 42.4} for index in range(14)]
        zones = normalize_public_chart_zones(
            [{"label": "suporte", "price": 42.33}, {"label": "resistencia", "price": 42.54}],
            symbol="ITUB4", timeframe="1M", rows=rows,
        )

        self.assertTrue(all(zone["status"] == "INSUFFICIENT_SEPARATION" for zone in zones))
        self.assertTrue(all(zone["operational"] is False for zone in zones))
        contract = routes_public_market_live._market_metrics_contract(
            "ITUB4", "1D", {"symbol": "ITUB4", "volume": 100, "average_volume": 100},
            {"summary": {"as_of": "2026-07-21T15:00:00Z"}, "zones": zones},
        )
        self.assertEqual(contract["levels"]["status"], "INSUFFICIENT_SEPARATION")
        self.assertEqual(contract["levels"]["micro_range"]["status"], "NON_OPERATIONAL")
        self.assertEqual(contract["levels"]["micro_range"]["timeframe"], "1M")

    def test_daily_volume_ratio_is_informational_and_intraday_rvol_stays_unavailable(self):
        contract = routes_public_market_live._market_metrics_contract(
            "ITUB4", "5M", {"symbol": "ITUB4", "volume": 70_400_000, "average_volume": 93_000_000}, {"summary": {}},
        )

        self.assertEqual(contract["volume_vs_daily_average"]["status"], "READY")
        self.assertAlmostEqual(contract["volume_vs_daily_average"]["ratio"], 0.757, places=3)
        self.assertTrue(contract["volume_vs_daily_average"]["informational_only"])
        self.assertEqual(contract["intraday_rvol"]["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(contract["intraday_rvol"]["rvol_ratio"])
        self.assertFalse(contract["intraday_rvol"]["operational_ready"])

    def test_sentiment_missing_impact_is_not_reported_as_neutral(self):
        contract = routes_public_market_live._market_metrics_contract(
            "PETR4", "1D", {"symbol": "PETR4"}, {"summary": {}},
            {"data_status": "READY", "items": [{"title": "Sem classificação", "is_stale": False}]},
        )

        sentiment = contract["sentiment"]
        self.assertEqual(sentiment["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(sentiment["value"])
        self.assertEqual(sentiment["reason"], "no_classified_sentiment")
        self.assertEqual(sentiment["components"]["missing_impact_count"], 1)

    def test_explicit_neutral_sentiment_remains_ready_and_counted(self):
        contract = routes_public_market_live._market_metrics_contract(
            "PETR4", "1D", {"symbol": "PETR4"}, {"summary": {}},
            {"data_status": "READY", "items": [{"impact": "neutral", "is_stale": False}]},
        )

        sentiment = contract["sentiment"]
        self.assertEqual(sentiment["status"], "READY")
        self.assertEqual(sentiment["value"], "neutral")
        self.assertEqual(sentiment["components"]["neutral_count"], 1)
        self.assertEqual(sentiment["components"]["classified_total"], 1)

    def test_operational_view_uses_flow_but_rejects_score_only_liquidity(self):
        daily = [{"time": f"2026-07-{index + 7:02d}T12:00:00Z", "close": 30 + index} for index in range(15)]
        ai_tools = {
            "status": "READY",
            "tools": {
                "flow": [{"canonical_symbol": "PETR4", "score": 61.2, "analysis_timeframe": "5m", "as_of": "2026-07-21T15:00:00Z", "freshness_status": "READY"}],
                "liquidity": [{"canonical_symbol": "PETR4", "score": 51.4, "state_label": "Armadilha de liquidez", "analysis_timeframe": "5m", "as_of": "2026-07-21T15:00:00Z", "freshness_status": "READY"}],
            },
        }
        contract = routes_public_market_live._market_metrics_contract(
            "PETR4", "1D", {"symbol": "PETR4", "volume": 108, "average_volume": 100},
            {"summary": {"trend_bias": "alta", "as_of": "2026-07-21T15:00:00Z"}, "rsi_metadata": {"timeframe": "5m"}, "zones": []},
            {"items": []},
            {"rsi": 61.6, "rsi_metadata": {"status": "AVAILABLE", "as_of": daily[-1]["time"]}, "master_score": 3.9},
            daily_rows=daily,
            ai_tools=ai_tools,
        )

        view = contract["operational_view"]
        self.assertEqual(view["technical_context"]["trend_d1"]["value"], "alta")
        self.assertEqual(view["technical_context"]["intraday_direction_5m"]["timeframe"], "5m")
        self.assertEqual(view["technical_context"]["institutional_flow"]["label"], "Comprador")
        self.assertEqual(view["technical_context"]["institutional_flow"]["value"], 61.2)
        self.assertEqual(view["technical_context"]["technical_bias"]["value"], "BULLISH")
        self.assertEqual(view["operational_context"]["liquidity"]["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(view["operational_context"]["liquidity"]["value"])
        self.assertEqual(view["operational_context"]["master_score"]["status"], "PARTIAL")
        self.assertEqual(view["operational_context"]["master_score"]["data_completeness"], 0.5714)
        self.assertEqual(len(view["operational_context"]["master_score"]["used_components"]), 4)

    def test_liquidity_requires_side_range_distance_timeframe_and_source(self):
        ai_tools = {
            "status": "READY",
            "tools": {"liquidity": [{
                "canonical_symbol": "PETR4", "score": 51.4, "price": 41.66,
                "candle_timeframe": "5m", "as_of": "2026-07-21T15:00:00Z",
                "source": "on_demand", "freshness_status": "READY",
                "metrics": {"lower_liquidity": 42.58, "upper_liquidity": 42.62},
            }]},
        }

        component = routes_public_market_live._ai_metric_component(ai_tools, "liquidity", "PETR4")

        self.assertEqual(component["status"], "READY")
        self.assertEqual(component["side"], "SELL_SIDE")
        self.assertEqual((component["low"], component["high"]), (42.58, 42.62))
        self.assertGreater(component["distance_from_price_pct"], 0)
        self.assertEqual(component["timeframe"], "5m")
        self.assertEqual(component["source"], "on_demand")

    def test_liquidity_map_envelope_is_ready_without_inventing_directional_side(self):
        ai_tools = {
            "status": "READY",
            "tools": {"liquidity": [{
                "canonical_symbol": "PETR4", "score": 55.0, "price": 100.0,
                "candle_timeframe": "5m", "as_of": "2026-07-26T15:00:00Z",
                "source": "on_demand", "freshness_status": "READY",
                "metrics": {"lower_liquidity": 92.5, "upper_liquidity": 107.5},
            }]},
        }

        component = routes_public_market_live._ai_metric_component(ai_tools, "liquidity", "PETR4")

        self.assertEqual(component["status"], "READY")
        self.assertEqual(component["side"], "BOTH_SIDES")
        self.assertEqual((component["low"], component["high"]), (92.5, 107.5))
        self.assertEqual(component["midpoint"], 100.0)
        self.assertEqual(component["distance_from_price_pct"], 0.0)
        self.assertEqual(component["reason"], "validated_liquidity_envelope")

    def test_completed_zero_confidence_is_preserved_but_pending_confidence_is_null(self):
        daily = [{"time": f"2026-07-{index + 7:02d}T12:00:00Z", "close": 30 + index} for index in range(15)]
        ai_tools = {
            "status": "READY",
            "tools": {
                "flow": [{"canonical_symbol": "PETR4", "score": 61.2, "candle_timeframe": "5m", "freshness_status": "READY"}],
                "liquidity": [{"canonical_symbol": "PETR4", "score": 51.4, "price": 41.66, "candle_timeframe": "5m", "as_of": "2026-07-21T15:00:00Z", "source": "on_demand", "freshness_status": "READY", "metrics": {"lower_liquidity": 42.58, "upper_liquidity": 42.62}}],
            },
        }
        metrics = {
            "session_date": "2026-07-21", "as_of": "2026-07-21T15:00:00Z",
            "intraday_rvol": {"status": "READY", "operational_ready": True},
            "sentiment": {"status": "READY"},
            "levels": {"status": "READY", "items": []},
        }
        insight = {
            "rsi": 61.6, "rsi_metadata": {"status": "AVAILABLE", "as_of": daily[-1]["time"]},
            "conviction_score": 0,
            "strategic_panel": {"master_confidence_pct": 0, "recommended_action": "AGUARDAR"},
        }

        completed = routes_public_market_live.build_symbol_operational_view(
            "PETR4", "1D", insight, metrics,
            chart={"summary": {"trend_bias": "alta"}}, daily_rows=daily, ai_tools=ai_tools,
        )
        pending = routes_public_market_live.build_symbol_operational_view(
            "PETR4", "1D", insight, {**metrics, "intraday_rvol": {"status": "PENDING"}},
            chart={"summary": {"trend_bias": "alta"}}, daily_rows=daily, ai_tools=ai_tools,
        )

        self.assertEqual(completed["confidence"], 0)
        self.assertEqual(completed["conviction"], 0)
        self.assertEqual(completed["confidence_status"], "READY")
        self.assertIsNone(pending["confidence"])
        self.assertIsNone(pending["conviction"])

    def test_stale_daily_candles_are_not_ready_or_operational(self):
        daily = [{"time": f"2026-07-{index + 3:02d}T12:00:00Z", "close": 30 + index} for index in range(15)]
        ai_tools = {
            "status": "READY",
            "tools": {
                "flow": [{"canonical_symbol": "PETR4", "score": 64.3, "candle_timeframe": "5m", "freshness_status": "READY"}],
                "liquidity": [{
                    "canonical_symbol": "PETR4", "score": 51.4, "price": 41.66,
                    "candle_timeframe": "5m", "as_of": "2026-07-21T15:00:00Z",
                    "source": "on_demand", "freshness_status": "READY",
                    "metrics": {"lower_liquidity": 42.58, "upper_liquidity": 42.62},
                }],
            },
        }
        metrics = {
            "session_date": "2026-07-21", "intraday_rvol": {"status": "READY"},
            "sentiment": {"status": "READY"}, "levels": {"status": "READY", "items": []},
        }
        insight = {
            "rsi": 61.6,
            "rsi_metadata": {"status": "AVAILABLE", "as_of": daily[-1]["time"], "source": "canonical_indicator_engine"},
            "strategic_panel": {"recommended_action": "COMPRAR"},
        }

        view = routes_public_market_live.build_symbol_operational_view(
            "PETR4", "1D", insight, metrics,
            chart={"summary": {"trend_bias": "alta", "as_of": "2026-07-21T15:00:00Z"}},
            daily_rows=daily, ai_tools=ai_tools,
        )

        self.assertEqual(view["technical_context"]["trend_d1"]["status"], "STALE")
        self.assertEqual(view["technical_context"]["rsi_d1"]["status"], "STALE")
        self.assertEqual(view["technical_context"]["trend_d1"]["freshness_status"], "STALE")
        self.assertEqual(view["technical_context"]["trend_d1"]["data_as_of"][:10], "2026-07-17")
        self.assertEqual(view["technical_context"]["trend_d1"]["session_date"], "2026-07-21")
        self.assertEqual(view["technical_context"]["trend_d1"]["age_sessions"], 2)
        self.assertEqual(view["technical_context"]["rsi_d1"]["age_sessions"], 2)
        self.assertEqual(view["decision"], "WAIT")
        self.assertEqual(
            {item["component"] for item in view["operational_blocks"]},
            {"trend_d1", "rsi_d1"},
        )

    def test_historical_news_never_becomes_ready_sentiment_or_a_trade(self):
        contract = routes_public_market_live._market_metrics_contract(
            "ABEV3", "1D", {"symbol": "ABEV3", "volume": 100, "average_volume": 100},
            {"summary": {}, "zones": [{"status": "INSUFFICIENT_SEPARATION"}]},
            {"items": [{"published_at": "2026-06-17T12:00:00Z", "is_stale": True, "freshness_bucket": "older"}]},
            {"trend_bias": "alta", "rsi": 61.0},
        )

        self.assertEqual(contract["sentiment"]["status"], "INSUFFICIENT_DATA")
        self.assertEqual(contract["sentiment"]["last_historical_source_at"], "2026-06-17T12:00:00Z")
        self.assertEqual(contract["operational_view"]["decision"], "WAIT")
        self.assertIsNone(contract["operational_view"]["confidence"])
        self.assertIn("levels", [item["component"] for item in contract["operational_view"]["pending_components"]])

    def test_pending_levels_remove_entry_without_erasing_technical_context(self):
        metrics = {"levels": {"status": "PENDING"}, "operational_view": {"operational_blocks": [{"component": "levels"}]}}
        insight = {"rsi": 61.6, "trend_bias": "alta", "strategic_panel": {"entry_reference": 41.67, "recommended_action": "COMPRAR"}}

        result = routes_public_market_live._gate_pending_operational_levels(insight, metrics)

        self.assertEqual(result["rsi"], 61.6)
        self.assertEqual(result["trend_bias"], "alta")
        self.assertIsNone(result["strategic_panel"]["entry_reference"])
        self.assertEqual(result["strategic_panel"]["operational_levels_block"]["levels"], {})
        self.assertEqual(result["strategic_panel"]["recommended_action"], "AGUARDAR")

    def test_ready_symbol_analysis_is_rehydrated_after_ttl(self):
        stale = {"status": "READY", "updated_at": "2026-07-21T00:00:00+00:00"}
        with patch.object(symbol_hydration, "_CACHE", {"PETR4:1D": stale}), patch.object(
            symbol_hydration, "_LOADED", True
        ), patch.object(symbol_hydration, "_RUNNING", set()), patch.object(
            symbol_hydration, "_store", return_value={}
        ), patch.object(symbol_hydration, "Thread") as thread, patch(
            "app.system.quote_warmup.request_on_demand_quote_warmup"
        ), patch("app.system.chart_warmup.request_on_demand_chart_warmup"), patch(
            "app.system.news_warmup.request_news_warmup"
        ):
            queued = symbol_hydration.request_symbol_hydration("PETR4", timeframe="1D")

        self.assertTrue(queued)
        thread.assert_called_once()

    def test_worker_timeout_becomes_terminal_with_missing_dependencies(self):
        with patch.object(symbol_hydration, "_quote", return_value={}), patch.object(
            symbol_hydration, "_chart", return_value=[]
        ), patch.object(symbol_hydration.time, "sleep"), patch.object(
            symbol_hydration, "_store"
        ) as store, patch.object(symbol_hydration, "_RUNNING", {"AAPL:1D"}):
            symbol_hydration._run("AAPL", "1D")

        terminal = store.call_args.kwargs
        self.assertEqual(terminal["status"], "INSUFFICIENT_DATA")
        self.assertEqual(terminal["reason"], "hydration_timeout_missing_dependencies")
        self.assertEqual(terminal["missing_components"], ["quote", "chart_intraday", "chart_daily"])

    def test_missing_intraday_volume_does_not_mark_existing_chart_missing(self):
        daily = [
            {"time": f"2026-07-{day:02d}T12:00:00Z", "open": 30, "high": 31, "low": 29, "close": 30 + day, "volume": 100}
            for day in range(1, 16)
        ]
        intraday = [
            {"time": f"2026-07-21T12:{minute:02d}:00Z", "open": 30, "high": 31, "low": 29, "close": 30, "volume": 100 if minute < 14 else 0}
            for minute in range(15)
        ]
        with patch.object(symbol_hydration, "_quote", return_value={"price": 30}), patch.object(
            symbol_hydration, "_chart", side_effect=lambda _symbol, interval: intraday if interval == "1D" else daily
        ), patch.object(symbol_hydration, "_store") as store, patch.object(
            symbol_hydration, "_RUNNING", {"AAPL:1D"}
        ):
            symbol_hydration._run("AAPL", "1D")

        terminal = store.call_args.kwargs
        self.assertEqual(terminal["status"], "INSUFFICIENT_DATA")
        self.assertEqual(terminal["missing_components"], ["intraday_volume"])

        with patch.object(symbol_hydration, "_quote", return_value={"price": 30}), patch.object(
            symbol_hydration, "_chart", side_effect=lambda _symbol, interval: intraday if interval == "1D" else daily
        ), patch.object(symbol_hydration, "get_symbol_analysis", return_value=terminal), patch.object(
            symbol_hydration, "get_news_cache_info", return_value={"age_seconds": 0}
        ):
            status = symbol_hydration.hydration_status("AAPL")

        self.assertEqual(status["chart_intraday"], "READY")
        self.assertEqual(status["ai"], "INSUFFICIENT_DATA")

    def test_fresh_terminal_analysis_is_not_requeued_on_every_poll(self):
        terminal = {
            "status": "INSUFFICIENT_DATA",
            "reason": "hydration_timeout_missing_dependencies",
            "updated_at": symbol_hydration._now(),
        }
        with patch.object(symbol_hydration, "_CACHE", {"AAPL:1D": terminal}), patch.object(
            symbol_hydration, "_LOADED", True
        ), patch.object(symbol_hydration, "_RUNNING", set()), patch.object(
            symbol_hydration, "Thread"
        ) as thread, patch("app.system.quote_warmup.request_on_demand_quote_warmup"), patch(
            "app.system.chart_warmup.request_on_demand_chart_warmup"
        ), patch("app.system.news_warmup.request_news_warmup"):
            queued = symbol_hydration.request_symbol_hydration("AAPL", timeframe="1D")

        self.assertFalse(queued)
        thread.assert_not_called()

    def test_legacy_pending_without_worker_requeues_with_lifecycle_clock(self):
        pending = {"status": "PENDING", "updated_at": "2026-07-21T11:00:00+00:00", "retry_count": 2}
        with patch.object(symbol_hydration, "_CACHE", {"AAPL:1D": pending}), patch.object(
            symbol_hydration, "_LOADED", True
        ), patch.object(symbol_hydration, "_RUNNING", set()), patch.object(
            symbol_hydration, "_now", return_value="2026-07-21T12:00:00+00:00"
        ), patch.object(symbol_hydration, "_store") as store, patch.object(
            symbol_hydration, "Thread"
        ) as thread, patch("app.system.quote_warmup.request_on_demand_quote_warmup"), patch(
            "app.system.chart_warmup.request_on_demand_chart_warmup"
        ), patch("app.system.news_warmup.request_news_warmup"):
            queued = symbol_hydration.request_symbol_hydration("AAPL", timeframe="1D")

        self.assertTrue(queued)
        self.assertEqual(store.call_args.kwargs["started_at"], "2026-07-21T12:00:00+00:00")
        self.assertEqual(store.call_args.kwargs["deadline_at"], "2026-07-21T12:00:12+00:00")
        self.assertEqual(store.call_args.kwargs["retry_count"], 3)
        thread.assert_called_once()

    def test_terminal_store_preserves_lifecycle_metadata(self):
        pending = {
            "status": "PENDING", "started_at": "2026-07-21T12:00:00+00:00",
            "deadline_at": "2026-07-21T12:00:12+00:00", "retry_count": 3,
        }
        with patch.object(symbol_hydration, "_CACHE", {"AAPL:1D": pending}), patch.object(
            symbol_hydration, "_LOADED", True
        ), patch.object(symbol_hydration, "_persist"), patch.object(
            symbol_hydration, "_now", return_value="2026-07-21T12:00:12+00:00"
        ):
            stored = symbol_hydration._store(
                "AAPL", "1D", status="INSUFFICIENT_DATA",
                reason="hydration_timeout_missing_dependencies", missing_components=["quote"],
            )

        self.assertEqual(stored["started_at"], pending["started_at"])
        self.assertEqual(stored["deadline_at"], pending["deadline_at"])
        self.assertEqual(stored["retry_count"], 3)

    def test_hydration_status_marks_stale_daily_cache(self):
        stale_daily = [{"time": f"2026-07-{index + 3:02d}T12:00:00Z", "close": 30 + index} for index in range(15)]
        with patch.object(symbol_hydration, "_quote", return_value={"quote_time": "2026-07-21T17:00:00-03:00"}), patch.object(
            symbol_hydration, "_chart", side_effect=lambda _symbol, interval: [{"close": 1}] if interval == "1D" else stale_daily
        ), patch.object(symbol_hydration, "get_symbol_analysis", return_value={"status": "READY"}), patch.object(
            symbol_hydration, "get_news_cache_info", return_value={"age_seconds": 0}
        ):
            status = symbol_hydration.hydration_status("AAPL")

        self.assertEqual(status["chart_daily"], "READY")
        self.assertEqual(status["rsi"], "STALE")

    def test_terminal_analysis_maps_missing_data_status_components(self):
        terminal = {
            "status": "INSUFFICIENT_DATA",
            "reason": "hydration_timeout_missing_dependencies",
            "missing_components": ["quote", "chart_daily"],
        }
        with patch.object(symbol_hydration, "_quote", return_value={}), patch.object(
            symbol_hydration, "_chart", side_effect=lambda _symbol, interval: [{"close": 1}] if interval == "1D" else []
        ), patch.object(symbol_hydration, "get_symbol_analysis", return_value=terminal), patch.object(
            symbol_hydration, "get_news_cache_info", return_value={"age_seconds": 0}
        ):
            status = symbol_hydration.hydration_status("AAPL")

        self.assertEqual(status["quote"], "INSUFFICIENT_DATA")
        self.assertEqual(status["chart_intraday"], "READY")
        self.assertEqual(status["chart_daily"], "INSUFFICIENT_DATA")
        self.assertEqual(status["rsi"], "INSUFFICIENT_DATA")
        self.assertEqual(status["ai"], "INSUFFICIENT_DATA")
        self.assertFalse(any(value in {"PENDING", "REFRESHING"} for value in status.values()))


if __name__ == "__main__":
    unittest.main()
