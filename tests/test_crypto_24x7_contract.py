import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_public_market_live
from app.market import market_data_loader
from app.services import news_service, public_news_service
from app.services.public_market_data_service import build_crypto_intraday_rvol_contract
from app.system import symbol_hydration


def _same_bucket_rows(*, prior_days: int = 20, current_volume: float = 200.0) -> list[dict]:
    current = datetime(2026, 7, 21, 12, 35, tzinfo=timezone.utc)
    rows: list[dict] = []
    for days_ago in range(prior_days, 0, -1):
        day = current - timedelta(days=days_ago)
        rows.extend([
            {"time": day.replace(minute=30).isoformat(), "close": 100.0, "volume": 10_000.0},
            {"time": day.isoformat(), "close": 100.0, "volume": 100.0},
        ])
    rows.append({"time": current.isoformat(), "close": 101.0, "volume": current_volume})
    return rows


class Crypto24x7ContractTests(unittest.TestCase):
    def test_crypto_identity_publishes_continuous_market_metadata(self):
        expected = {
            "BNBUSDT": ("BNBUSD", "BNB-USD"),
            "BTCUSDT": ("BTCUSD", "BTC-USD"),
            "ETHUSDT": ("ETHUSD", "ETH-USD"),
        }

        for requested, (canonical, provider) in expected.items():
            with self.subTest(requested=requested):
                contract = market_data_loader._identity_contract_for_symbol(requested)
                self.assertEqual(contract["canonical_symbol"], canonical)
                self.assertEqual(contract["provider_symbol"], provider)
                self.assertEqual(contract["asset_type"], "CRYPTO")
                self.assertEqual(contract["asset_class"], "crypto")
                self.assertEqual(contract["market_schedule"], "24x7")
                self.assertEqual(contract["session_timezone"], "UTC")
                self.assertEqual(contract["market_status"], "OPEN")

    def test_explicit_five_minute_history_uses_one_month_and_keeps_more_than_240_rows(self):
        frame = pd.DataFrame(
            {
                "Open": 100.0,
                "High": 101.0,
                "Low": 99.0,
                "Close": 100.0,
                "Volume": 1000.0,
            },
            index=pd.date_range("2026-07-01", periods=6000, freq="5min", tz="UTC"),
        )

        legacy_cache = [{"time": str(index), "close": 100.0, "volume": 1000.0} for index in range(240)]
        with patch.object(market_data_loader, "get_cached_chart_data", return_value=legacy_cache), patch.object(
            market_data_loader, "_network_provider_allowed", return_value=True
        ), patch.object(market_data_loader, "get_ticker_frame", return_value=frame) as get_frame, patch.object(
            market_data_loader, "_cache_chart_data", side_effect=lambda _symbol, _interval, rows: rows
        ):
            rows = market_data_loader.get_chart_data("BTCUSDT", "@5M")

        self.assertEqual(len(rows), 6000)
        get_frame.assert_called_once_with("BTCUSDT", period="1mo", interval="5m", auto_adjust=False)

    def test_crypto_hydration_requests_dedicated_five_minute_cache(self):
        with patch.object(symbol_hydration, "_CACHE", {}), patch.object(
            symbol_hydration, "_LOADED", True
        ), patch.object(symbol_hydration, "_RUNNING", set()), patch.object(
            symbol_hydration, "_store", return_value={}
        ), patch.object(symbol_hydration, "Thread"), patch(
            "app.system.quote_warmup.request_on_demand_quote_warmup"
        ), patch("app.system.chart_warmup.request_on_demand_chart_warmup") as chart_warmup, patch(
            "app.system.news_warmup.request_news_warmup"
        ):
            symbol_hydration.request_symbol_hydration("BNBUSDT", timeframe="1D")

        requested_symbol, intervals = chart_warmup.call_args.args
        self.assertEqual(requested_symbol, "BNBUSD")
        self.assertIn("@5M", intervals)

    def test_crypto_rvol_uses_only_same_utc_bucket_median(self):
        contract = build_crypto_intraday_rvol_contract("BTCUSDT", _same_bucket_rows())

        self.assertEqual(contract["symbol"], "BTCUSD")
        self.assertEqual(contract["status"], "READY")
        self.assertEqual(contract["baseline"], "same_utc_bucket_median")
        self.assertEqual(contract["sample_count"], 20)
        self.assertFalse(contract["weekday_split"])
        self.assertEqual(contract["rvol_ratio"], 2.0)
        self.assertEqual(contract["rvol_percent"], 200.0)

        insufficient = build_crypto_intraday_rvol_contract("BTCUSDT", _same_bucket_rows(prior_days=6))
        self.assertEqual(insufficient["status"], "INSUFFICIENT_DATA")
        self.assertEqual(insufficient["reason"], "insufficient_same_utc_bucket_samples")
        self.assertIsNone(insufficient["rvol_ratio"])

    def test_crypto_orderflow_proxies_are_terminal_unsupported(self):
        daily = [
            {"time": f"2026-07-{day:02d}T12:00:00+00:00", "close": 100 + day}
            for day in range(7, 22)
        ]
        ai_tools = {
            "status": "READY",
            "tools": {
                "flow": [{"canonical_symbol": "BNBUSD", "score": 75, "freshness_status": "READY"}],
                "liquidity": [{
                    "canonical_symbol": "BNBUSD", "score": 80, "price": 580,
                    "as_of": "2026-07-21T12:35:00+00:00", "source": "on_demand",
                    "freshness_status": "READY", "metrics": {"lower_liquidity": 590, "upper_liquidity": 595},
                }],
            },
        }
        metrics = {
            "session_date": "2026-07-21",
            "intraday_rvol": {"status": "READY", "operational_ready": True},
            "sentiment": {"status": "UNSUPPORTED", "reason": "no_current_crypto_news_sentiment"},
            "levels": {"status": "READY", "items": []},
        }
        insight = {
            "rsi": 55.0,
            "rsi_metadata": {"status": "AVAILABLE", "as_of": daily[-1]["time"]},
            "master_score": 6.2,
        }

        view = routes_public_market_live.build_symbol_operational_view(
            "BNBUSDT", "1D", insight, metrics,
            chart={"summary": {"trend_bias": "alta", "as_of": "2026-07-21T12:35:00+00:00"}},
            daily_rows=daily,
            ai_tools=ai_tools,
        )

        flow = view["technical_context"]["institutional_flow"]
        liquidity = view["operational_context"]["liquidity"]
        score = view["operational_context"]["master_score"]
        self.assertEqual(flow["status"], "UNSUPPORTED")
        self.assertEqual(liquidity["status"], "UNSUPPORTED")
        self.assertEqual(flow["reason"], "provider_has_no_crypto_orderflow")
        self.assertEqual(view["technical_context"]["technical_bias"]["value"], "BULLISH")
        self.assertEqual(view["decision"], "WAIT")
        self.assertEqual(score["status"], "PARTIAL")
        self.assertEqual(set(score["unsupported_components"]), {"flow", "sentiment", "liquidity"})
        self.assertEqual(score["missing_components"], [])
        self.assertEqual(score["data_completeness"], 1.0)

    def test_crypto_bundle_reads_cached_rvol_and_publishes_24x7_metadata(self):
        app = FastAPI()
        app.include_router(routes_public_market_live.router)
        quote = {
            "symbol": "BNBUSD", "canonical_symbol": "BNBUSD", "provider_symbol": "BNB-USD",
            "price": 580.0, "volume": 1000.0, "average_volume": 900.0,
            "quote_time": "2026-07-21T12:35:00+00:00",
        }
        daily = [
            {"time": f"2026-07-{day:02d}T12:00:00+00:00", "close": 100 + day}
            for day in range(7, 22)
        ]
        chart = {
            "ticker": "BNBUSD", "ohlc": [], "zones": [],
            "summary": {"trend_bias": "alta", "as_of": "2026-07-21T12:35:00+00:00"},
        }
        insight = {
            "symbol": "BNBUSD", "rsi": 55.0,
            "rsi_metadata": {"status": "AVAILABLE", "as_of": daily[-1]["time"]},
            "master_score": 6.2,
        }

        with patch.object(routes_public_market_live, "request_symbol_hydration"), patch.object(
            routes_public_market_live, "cached_price_payloads", return_value={"BNBUSD": quote}
        ), patch.object(routes_public_market_live, "_resolve_cached_quote", return_value=quote), patch.object(
            routes_public_market_live, "public_market_insight", return_value=insight
        ), patch.object(routes_public_market_live, "public_market_chart", return_value=chart), patch.object(
            routes_public_market_live, "build_public_news_payload",
            return_value={"items": [], "data_status": "UNSUPPORTED"},
        ), patch.object(
            routes_public_market_live, "build_public_ai_tools_payload", return_value={"status": "READY", "tools": {}}
        ), patch.object(routes_public_market_live, "get_symbol_analysis", return_value={}), patch.object(
            routes_public_market_live, "_load_chart_data_fast", return_value=daily
        ), patch.object(
            routes_public_market_live, "load_public_chart_rows", return_value=_same_bucket_rows()
        ), patch.object(routes_public_market_live, "hydration_status", return_value={}):
            payload = TestClient(app).get("/public/market/bundle/BNBUSDT?interval=1D").json()

        metrics = payload["market_metrics"]
        self.assertEqual(payload["asset_class"], "crypto")
        self.assertEqual(payload["market_schedule"], "24x7")
        self.assertEqual(payload["market_status"], "OPEN")
        self.assertEqual(metrics["canonical_symbol"], "BNBUSD")
        self.assertEqual(metrics["session_timezone"], "UTC")
        self.assertEqual(metrics["intraday_rvol"]["status"], "READY")
        self.assertEqual(metrics["intraday_rvol"]["rvol_ratio"], 2.0)

    def test_old_crypto_news_is_historical_and_bnb_uses_provider_aliases(self):
        old_item = {
            "id": "bnb-old", "ticker": "BNBUSD", "title": "BNB Chain historical update",
            "source": "Yahoo Finance", "url": "https://finance.yahoo.com/news/bnb-chain-old",
            "published_at_source": "2026-01-25T12:00:00+00:00", "direct_ticker_match": True,
        }
        with patch.object(public_news_service, "get_cached_symbol_news", return_value=[old_item]), patch.object(
            public_news_service, "get_news_cached_report", return_value={"status": "ok"}
        ), patch.object(
            public_news_service, "get_news_cache_info",
            return_value={"status": "warm", "provider_status": "ok", "provider": "yfinance", "age_seconds": 0},
        ):
            payload = public_news_service.build_public_news_payload("BNBUSDT", allow_fetch=False)

        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["data_status"], "HISTORICAL")
        self.assertEqual(payload["status"], "historical")
        self.assertNotEqual(payload["data_status"], "READY")
        self.assertIn("BNB-USD", news_service._news_ticker_candidates("BNBUSDT"))
        self.assertTrue({"bnb", "binance coin", "bnb chain"}.issubset(news_service._news_aliases("BNBUSD")))


if __name__ == "__main__":
    unittest.main()
