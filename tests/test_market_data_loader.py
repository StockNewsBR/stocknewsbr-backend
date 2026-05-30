import unittest
from unittest.mock import patch

from app.market import market_data_loader
from app.system.system_metrics import provider_call_context


class MarketDataLoaderTests(unittest.TestCase):
    def setUp(self):
        market_data_loader._SYMBOL_FAILURES.clear()

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
                {"symbol": "ES", "provider_symbol": "ES=F", "price": 7538.0},
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
                "symbol": "META34",
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
            payloads = market_data_loader.get_price_snapshots(["META34.SA"])

        batch_download.assert_called_once()
        self.assertEqual(batch_download.call_args.args[0], ["META34"])
        get_price_snapshot.assert_called_once_with("META34")
        self.assertEqual(payloads["META34"]["symbol"], "META34")
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
