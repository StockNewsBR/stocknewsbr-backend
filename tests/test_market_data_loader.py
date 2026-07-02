import unittest
from unittest.mock import patch

import pandas as pd

from app.market import market_data_loader
from app.services.symbol_sanitizer import clear_symbol_cooldown
from app.system.system_metrics import provider_call_context


class EmptyDownload:
    empty = True


class FakeYFinance:
    def __init__(self):
        self.calls = []

    def download(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        return EmptyDownload()


class MarketDataLoaderTests(unittest.TestCase):
    def setUp(self):
        market_data_loader._SYMBOL_FAILURES.clear()
        with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
            market_data_loader._PRICE_SNAPSHOT_CACHE.clear()
        for symbol in ("BTCUSD", "BTC-USD", "BTCUSDT", "DOGEUSD", "DOGE-USD", "ADAUSD", "SOLUSD", "LINKUSD", "AVAXUSD", "ETHUSD"):
            clear_symbol_cooldown(symbol)

    def test_cme_and_b3_futures_normalize_to_provider_symbols(self):
        self.assertEqual(market_data_loader._normalize_symbol("NQ"), "NQ=F")
        self.assertEqual(market_data_loader._normalize_symbol("MNQ"), "MNQ=F")
        self.assertEqual(market_data_loader._normalize_symbol("MNO"), "MNQ=F")
        self.assertEqual(market_data_loader._normalize_symbol("ES"), "ES=F")
        self.assertEqual(market_data_loader._normalize_symbol("MES"), "MES=F")
        self.assertEqual(market_data_loader._normalize_symbol("MYM"), "MYM=F")
        self.assertEqual(market_data_loader._normalize_symbol("WINM26"), "WINM26.SA")
        self.assertEqual(market_data_loader._normalize_symbol("WDOM26"), "WDOM26.SA")
        self.assertEqual(market_data_loader._normalize_symbol("AMZN34"), "AMZO34.SA")
        self.assertEqual(market_data_loader._normalize_symbol("META34"), "M1TA34.SA")

        self.assertEqual(market_data_loader.get_display_symbol("NQ"), "NQ")
        self.assertEqual(market_data_loader.get_display_symbol("MNO"), "MNO")
        self.assertEqual(market_data_loader.get_display_symbol("WINM26"), "WINM26")

    def test_crypto_symbols_normalize_to_yahoo_provider_symbols(self):
        expected = {
            "BTCUSD": "BTC-USD",
            "ETHUSD": "ETH-USD",
            "DOGEUSD": "DOGE-USD",
            "ADAUSD": "ADA-USD",
            "SOLUSD": "SOL-USD",
            "LINKUSD": "LINK-USD",
            "AVAXUSD": "AVAX-USD",
        }

        for display_symbol, provider_symbol in expected.items():
            with self.subTest(display_symbol=display_symbol):
                self.assertEqual(market_data_loader._normalize_symbol(display_symbol), provider_symbol)
                self.assertEqual(market_data_loader.get_display_symbol(display_symbol), display_symbol)

        self.assertEqual(market_data_loader._normalize_symbol("BTCUSDT"), "BTC-USD")
        self.assertEqual(market_data_loader.get_display_symbol("BTCUSDT"), "BTCUSD")
        self.assertEqual(market_data_loader._normalize_symbol("PETR4"), "PETR4.SA")
        self.assertEqual(market_data_loader._normalize_symbol("TSLA"), "TSLA")

    def test_batch_download_sends_crypto_provider_symbol_to_yfinance(self):
        fake_yf = FakeYFinance()

        with patch.object(market_data_loader, "_get_yfinance", return_value=fake_yf), patch.object(
            market_data_loader, "record_external_provider_call"
        ), patch.object(market_data_loader, "record_worker_stage_duration"):
            self.assertIsNone(market_data_loader.batch_download(["DOGEUSD"], period="1d", interval="5m"))

        self.assertEqual(fake_yf.calls[0]["kwargs"]["tickers"], ["DOGE-USD"])
        self.assertNotIn("DOGEUSD", fake_yf.calls[0]["kwargs"]["tickers"])

    def test_crypto_snapshot_preserves_display_and_provider_symbols(self):
        frame = pd.DataFrame(
            [
                {"Open": 0.10, "High": 0.11, "Low": 0.09, "Close": 0.10, "Volume": 1_000_000},
                {"Open": 0.10, "High": 0.12, "Low": 0.10, "Close": 0.12, "Volume": 2_000_000},
            ],
            index=pd.date_range("2026-01-01", periods=2, freq="h"),
        )

        with patch.object(market_data_loader, "batch_download", return_value=frame) as download:
            payload = market_data_loader.get_price_snapshot("DOGEUSD")

        download.assert_called_once_with(["DOGE-USD"], period="5d", interval="30m")
        self.assertIsNotNone(payload)
        self.assertEqual(payload["provider_symbol"], "DOGE-USD")
        self.assertEqual(payload["display_symbol"], "DOGEUSD")
        self.assertEqual(payload["symbol"], "DOGEUSD")
        self.assertEqual(payload["price"], 0.12)

    def test_cme_future_rejects_old_equity_cache_payload(self):
        self.assertFalse(
            market_data_loader._payload_matches_requested_symbol(
                "ES",
                {"symbol": "ES", "price": 68.78},
            )
        )
        self.assertTrue(
            market_data_loader._payload_matches_requested_symbol(
                "ES",
                {"symbol": "ES", "provider_symbol": "ES=F", "price": 7538.0, "price_semantics": "direct_market_price"},
            )
        )

    def test_b3_future_reference_proxy_is_explicit_not_exact_contract(self):
        with patch.object(
            market_data_loader,
            "_get_cached_price_payload",
            return_value={"symbol": "^BVSP", "provider_symbol": "^BVSP", "price": 179000.0, "change": 120.0, "change_pct": 0.07},
        ):
            payload = market_data_loader._reference_payload_for_b3_future("WINM26")

        self.assertIsNotNone(payload)
        self.assertEqual(payload["symbol"], "WINM26")
        self.assertEqual(payload["source"], "reference_proxy")
        self.assertEqual(payload["reference_symbol"], "^BVSP")
        self.assertFalse(payload["exact_contract"])
        self.assertTrue(market_data_loader._payload_matches_requested_symbol("WINM26", payload))

    def test_bdr_batch_snapshots_prefer_b3_brl_provider_before_us_proxy(self):
        with patch.object(
            market_data_loader,
            "get_cached_price_snapshots",
            return_value={},
        ), patch.object(
            market_data_loader,
            "batch_download",
            return_value=None,
        ) as batch_download, patch.object(
            market_data_loader,
            "_get_cached_price_payload",
            return_value=None,
        ), patch.object(
            market_data_loader,
            "get_price_snapshot",
            return_value={
                "symbol": "M1TA34",
                "provider_symbol": "M1TA34.SA",
                "price": 83.2,
                "change": 0.4,
                "change_pct": 0.48,
                "source": "market",
            },
        ) as get_price_snapshot, patch.object(
            market_data_loader,
            "_persist_price_cache",
        ):
            payloads = market_data_loader.get_price_snapshots(["M1TA34.SA"])

        batch_download.assert_called_once()
        self.assertEqual(batch_download.call_args.args[0], ["META34"])
        get_price_snapshot.assert_called_once_with("META34")
        self.assertEqual(payloads["META34"]["symbol"], "META34")
        self.assertEqual(payloads["META34"]["requested_symbol"], "META34")
        self.assertEqual(payloads["META34"]["display_symbol"], "META34")
        self.assertEqual(payloads["META34"]["canonical_symbol"], "M1TA34")
        self.assertEqual(payloads["META34"]["provider_symbol"], "M1TA34.SA")
        self.assertEqual(payloads["META34"]["source"], "market")
        self.assertEqual(payloads["META34"]["price"], 83.2)

    def test_bdr_rejects_cached_us_proxy_payload(self):
        self.assertFalse(
            market_data_loader._payload_matches_requested_symbol(
                "AMD34",
                {
                    "symbol": "AMD34",
                    "provider_symbol": "AMD",
                    "price": 422.4,
                    "source": "proxy_market",
                },
            )
        )

    def test_provider_failure_cooldown_skips_live_snapshot_fetch(self):
        market_data_loader._SYMBOL_FAILURES.clear()
        market_data_loader._mark_symbol_failure("AAPL", error="empty_price")

        with patch.object(
            market_data_loader,
            "_get_cached_price_payload",
            return_value=None,
        ) as cached, patch.object(
            market_data_loader,
            "get_ticker_frame",
            side_effect=AssertionError("cooldown must not call yfinance"),
        ), patch.object(
            market_data_loader,
            "_price_payload_from_fast_info",
            side_effect=AssertionError("cooldown must not call fast_info"),
        ):
            payload = market_data_loader.get_price_snapshot("AAPL")

        self.assertIsNone(payload)
        cached.assert_called_once_with("AAPL", allow_stale=True)
        self.assertTrue(market_data_loader._is_symbol_cooling_down("AAPL"))
        market_data_loader._SYMBOL_FAILURES.clear()
        self.assertTrue(
            market_data_loader._payload_matches_requested_symbol(
                "AMD34",
                {
                    "symbol": "AMD34",
                    "provider_symbol": "A1MD34.SA",
                    "price": 89.72,
                    "source": "market",
                    "price_semantics": "direct_market_price",
                },
            )
        )

    def test_http_context_blocks_live_price_fetch_and_returns_cache_only(self):
        with patch.object(
            market_data_loader,
            "_get_cached_price_payload",
            return_value={"symbol": "AAPL", "price": 190.0, "volume": 1000, "source": "stale_market_cache"},
        ) as cached, patch.object(
            market_data_loader,
            "get_ticker_frame",
            side_effect=AssertionError("http context must not download"),
        ), patch.object(
            market_data_loader,
            "_price_payload_from_fast_info",
            side_effect=AssertionError("http context must not call fast_info"),
        ):
            with provider_call_context("http"):
                payload = market_data_loader.get_price_snapshot("AAPL")

        self.assertEqual(payload["price"], 190.0)
        cached.assert_called_once_with("AAPL", allow_stale=True)

    def test_http_context_blocks_batch_fetch_and_uses_cached_snapshots(self):
        with patch.object(
            market_data_loader,
            "get_cached_price_snapshots",
            return_value={"AAPL": {"symbol": "AAPL", "price": 190.0, "volume": 1000}},
        ) as cached, patch.object(
            market_data_loader,
            "batch_download",
            side_effect=AssertionError("http context must not download"),
        ):
            with provider_call_context("http"):
                payloads = market_data_loader.get_price_snapshots(["AAPL"])

        self.assertEqual(payloads["AAPL"]["price"], 190.0)
        cached.assert_called_once_with(["AAPL"], allow_stale=True)


if __name__ == "__main__":
    unittest.main()
