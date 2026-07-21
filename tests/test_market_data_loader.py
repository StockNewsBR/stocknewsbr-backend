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
        self.assertEqual(market_data_loader._normalize_symbol("AXIA7"), "AXIA7.SA")
        self.assertEqual(market_data_loader._normalize_symbol("AXIA3"), "AXIA3.SA")
        self.assertEqual(market_data_loader._normalize_symbol("PETR4"), "PETR4.SA")
        self.assertEqual(market_data_loader._normalize_symbol("TSLA"), "TSLA")
        self.assertEqual(market_data_loader.get_display_symbol("AXIA7"), "AXIA7")
        self.assertEqual(market_data_loader.get_display_symbol("AXIA3"), "AXIA3")
        self.assertEqual(market_data_loader.get_display_symbol("PETR4"), "PETR4")
        self.assertEqual(market_data_loader.get_display_symbol("TSLA"), "TSLA")

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
        self.assertEqual(batch_download.call_args.args[0], ["M1TA34"])
        get_price_snapshot.assert_called_once_with("M1TA34")
        self.assertEqual(payloads["M1TA34"]["symbol"], "M1TA34")
        self.assertEqual(payloads["M1TA34"]["display_symbol"], "M1TA34")
        self.assertEqual(payloads["M1TA34"]["canonical_symbol"], "M1TA34")
        self.assertEqual(payloads["M1TA34"]["provider_symbol"], "M1TA34.SA")
        self.assertEqual(payloads["M1TA34"]["source"], "market")
        self.assertEqual(payloads["M1TA34"]["price"], 83.2)

    def test_legacy_aliases_keep_canonical_snapshot_and_cache_identity(self):
        expected_provider_symbols = {
            "AXIA3": "AXIA3.SA",
            "AXIA7": "AXIA7.SA",
            "AMZO34": "AMZO34.SA",
            "M1TA34": "M1TA34.SA",
            "A1MD34": "A1MD34.SA",
        }
        aliases = {
            "ELET3": "AXIA3",
            "ELET6": "AXIA3",
            "AXIA6": "AXIA3",
            "AMZN34": "AMZO34",
            "META34": "M1TA34",
            "AMD34": "A1MD34",
        }
        for alias, canonical in aliases.items():
            with self.subTest(alias=alias):
                self.assertEqual(market_data_loader.get_display_symbol(alias), canonical)
                self.assertEqual(market_data_loader._normalize_symbol(alias), expected_provider_symbols[canonical])

        frame = pd.DataFrame(
            [
                {"Open": 10.0, "High": 10.5, "Low": 9.5, "Close": 10.0, "Volume": 1_000},
                {"Open": 10.0, "High": 11.5, "Low": 9.8, "Close": 11.0, "Volume": 2_000},
            ],
            index=pd.date_range("2026-01-01", periods=2, freq="h"),
        )

        def snapshot_for(symbol):
            return market_data_loader._price_payload_from_frame(symbol, frame)

        requested = [
            "ELET3",
            "AXIA3",
            "ELET6",
            "AXIA7",
            "AMZN34",
            "AMZO34",
            "META34",
            "M1TA34",
            "AMD34",
            "A1MD34",
        ]
        with patch.object(market_data_loader, "get_cached_price_snapshots", return_value={}), patch.object(
            market_data_loader, "batch_download", return_value=None
        ) as batch_download, patch.object(
            market_data_loader, "get_price_snapshot", side_effect=snapshot_for
        ), patch.object(market_data_loader, "_persist_price_cache"):
            payloads = market_data_loader.get_price_snapshots(requested, force_refresh=True)

        canonical_symbols = set(expected_provider_symbols)
        self.assertEqual(set(payloads), canonical_symbols)
        self.assertEqual(batch_download.call_args.args[0], ["AXIA3", "AXIA7", "AMZO34", "M1TA34", "A1MD34"])
        for canonical, expected_provider in expected_provider_symbols.items():
            with self.subTest(canonical=canonical):
                self.assertEqual(payloads[canonical]["symbol"], canonical)
                self.assertEqual(payloads[canonical]["display_symbol"], canonical)
                self.assertEqual(payloads[canonical]["canonical_symbol"], canonical)
                self.assertEqual(payloads[canonical]["provider_symbol"], expected_provider)

        with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
            self.assertTrue(canonical_symbols.issubset(market_data_loader._PRICE_SNAPSHOT_CACHE))
            self.assertTrue(set(aliases).isdisjoint(market_data_loader._PRICE_SNAPSHOT_CACHE))
            self.assertEqual(market_data_loader._PRICE_SNAPSHOT_CACHE["AXIA3"]["payload"]["provider_symbol"], "AXIA3.SA")
            self.assertEqual(market_data_loader._PRICE_SNAPSHOT_CACHE["AXIA7"]["payload"]["provider_symbol"], "AXIA7.SA")

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

    def test_change_uses_previous_session_close_not_previous_candle(self):
        """PETR4 reported "+0,03 (+0,07%)" while Yahoo showed "+0,52 (+1,27%)".

        Same price, wrong baseline: the payload compared the last intraday candle
        instead of the previous SESSION close. Pins change == price - X.
        """
        previous_session_close = 40.90
        rows = [
            # Previous session: its LAST close is the only valid baseline.
            {"Open": 40.41, "High": 41.11, "Low": 40.41, "Close": 40.50, "Volume": 1_000},
            {"Open": 40.50, "High": 41.11, "Low": 40.41, "Close": previous_session_close, "Volume": 1_000},
            # Current session: consecutive candles move only a few cents.
            {"Open": 41.20, "High": 41.44, "Low": 40.47, "Close": 41.39, "Volume": 2_000},
            {"Open": 41.39, "High": 41.44, "Low": 41.33, "Close": 41.42, "Volume": 2_000},
        ]
        index = [
            pd.Timestamp("2026-07-17 17:30:00", tz="UTC"),
            pd.Timestamp("2026-07-17 19:30:00", tz="UTC"),
            pd.Timestamp("2026-07-20 17:30:00", tz="UTC"),
            pd.Timestamp("2026-07-20 19:30:00", tz="UTC"),
        ]
        frame = pd.DataFrame(rows, index=pd.DatetimeIndex(index))

        with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
            market_data_loader._CHART_DATA_CACHE.clear()
        payload = market_data_loader._price_payload_from_frame("PETR4", frame)

        self.assertEqual(payload["price"], 41.42)
        self.assertEqual(payload["previous_close"], previous_session_close)
        self.assertEqual(payload["change"], round(41.42 - previous_session_close, 4))
        self.assertEqual(payload["change_pct"], round((41.42 - previous_session_close) / previous_session_close * 100, 4))
        # The previous-candle delta (+0.03) is exactly the reported bug.
        self.assertNotEqual(payload["change"], 0.03)
        self.assertEqual(payload["quote_time"], "2026-07-20T16:30:00-03:00")
        self.assertIsNone(payload["market_state"])

    def test_previous_session_close_helper_is_shared_and_timezone_aware(self):
        # US post-market rolls the UTC day forward; the session day must be read in
        # the exchange timezone or the baseline picks today's own regular close.
        stamps = [
            pd.Timestamp("2026-07-17 20:00:00", tz="UTC"),
            pd.Timestamp("2026-07-20 19:59:00", tz="UTC"),
            pd.Timestamp("2026-07-20 23:30:00", tz="UTC"),
        ]
        closes = [190.0, 200.0, 201.0]
        self.assertEqual(
            market_data_loader.previous_session_close(stamps, closes, "America/New_York"),
            190.0,
        )
        # Chart-cache rows arrive as ISO strings and must work with the same helper.
        self.assertEqual(
            market_data_loader.previous_session_close(
                ["2026-07-17 00:00:00+00:00", "2026-07-20 00:00:00+00:00"],
                [40.90, 41.42],
            ),
            40.90,
        )
        self.assertIsNone(market_data_loader.previous_session_close(["2026-07-20 00:00:00+00:00"], [41.42]))
        self.assertEqual(
            market_data_loader.session_change(41.42, 40.90),
            {"change": 0.52, "change_pct": 1.2714, "previous_close": 40.9},
        )

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
