import unittest
from importlib import import_module
from unittest.mock import patch

market_data_cache_module = import_module("app.cache.market_data_cache")
symbol_sanitizer = import_module("app.services.symbol_sanitizer")
system_metrics = import_module("app.system.system_metrics")


class FakeYFinance:
    def __init__(self):
        self.calls = 0
        self.last_kwargs = {}

    def download(self, *args, **kwargs):
        self.calls += 1
        self.last_kwargs = dict(kwargs)
        return []


class MarketDataCacheTests(unittest.TestCase):
    def setUp(self):
        market_data_cache_module._cache_data = None
        market_data_cache_module._cache_key = tuple()
        market_data_cache_module._last_update = 0.0
        market_data_cache_module._provider_cooldown_until = 0.0
        market_data_cache_module._last_provider_failure_log = 0.0
        for symbol in ("DOGEUSD", "DOGE-USD", "ADAUSD", "ADA-USD", "PETR4.SA", "TSLA"):
            symbol_sanitizer.clear_symbol_cooldown(symbol)

    def tearDown(self):
        self.setUp()

    def test_empty_provider_response_starts_cooldown(self):
        fake_yf = FakeYFinance()

        with patch.object(market_data_cache_module, "_get_yfinance", return_value=fake_yf), \
            patch.object(market_data_cache_module, "record_external_provider_call"), \
            patch.object(market_data_cache_module, "record_worker_stage_duration") as record_stage, \
            patch.object(market_data_cache_module.logger, "warning"):
            self.assertIsNone(market_data_cache_module.fetch_market_data(("PETR4.SA",)))
            self.assertIsNone(market_data_cache_module.fetch_market_data(("VALE3.SA",)))

        self.assertEqual(fake_yf.calls, 1)
        record_stage.assert_any_call("market_download_cooldown", 0.0, success=False)

    def test_http_context_blocks_provider_download(self):
        fake_yf = FakeYFinance()

        with patch.object(market_data_cache_module, "_get_yfinance", return_value=fake_yf), \
            patch.object(market_data_cache_module, "record_external_provider_call") as record_provider:
            with system_metrics.provider_call_context("http"):
                self.assertIsNone(market_data_cache_module.fetch_market_data(("PETR4.SA",)))

        self.assertEqual(fake_yf.calls, 0)
        record_provider.assert_called_once()

    def test_normalizes_crypto_to_provider_symbol_before_download(self):
        normalized = market_data_cache_module._normalize_tickers(["DOGEUSD", "ADAUSD", "PETR4.SA", "TSLA"])

        self.assertEqual(normalized, ("DOGE-USD", "ADA-USD", "PETR4.SA", "TSLA"))

    def test_yfinance_does_not_receive_raw_crypto_display_symbol(self):
        fake_yf = FakeYFinance()

        with patch.object(market_data_cache_module, "_get_yfinance", return_value=fake_yf), \
            patch.object(market_data_cache_module, "record_external_provider_call"), \
            patch.object(market_data_cache_module, "record_worker_stage_duration"), \
            patch.object(market_data_cache_module.logger, "warning"):
            self.assertIsNone(market_data_cache_module.get_market_data(["DOGEUSD"]))

        self.assertEqual(fake_yf.calls, 1)
        self.assertEqual(fake_yf.last_kwargs["tickers"], ["DOGE-USD"])
        self.assertNotIn("DOGEUSD", fake_yf.last_kwargs["tickers"])


if __name__ == "__main__":
    unittest.main()
