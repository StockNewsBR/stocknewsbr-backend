import unittest
from importlib import import_module
from unittest.mock import patch

market_data_cache_module = import_module("app.cache.market_data_cache")
system_metrics = import_module("app.system.system_metrics")


class FakeYFinance:
    def __init__(self):
        self.calls = 0

    def download(self, *args, **kwargs):
        self.calls += 1
        return []


class MarketDataCacheTests(unittest.TestCase):
    def setUp(self):
        market_data_cache_module._cache_data = None
        market_data_cache_module._cache_key = tuple()
        market_data_cache_module._last_update = 0.0
        market_data_cache_module._provider_cooldown_until = 0.0
        market_data_cache_module._last_provider_failure_log = 0.0

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


if __name__ == "__main__":
    unittest.main()
