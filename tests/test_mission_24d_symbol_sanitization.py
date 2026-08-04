import importlib
import time
import unittest
from unittest.mock import patch

import worker
from app.market import market_data_loader
from app.services.snapshot_runtime_status import (
    SNAPSHOT_RUNTIME_CRITICAL,
    SNAPSHOT_RUNTIME_HEALTHY,
    attach_snapshot_runtime_status,
)
from app.services.symbol_sanitizer import (
    clear_symbol_cooldown,
    is_symbol_on_cooldown,
    sanitize_market_symbol,
)
from app.system import chart_warmup, news_warmup, quote_warmup

market_data_cache_module = importlib.import_module("app.cache.market_data_cache")


class SingleCycleStopEvent:
    def __init__(self):
        self.wait_calls = 0

    def is_set(self):
        return self.wait_calls > 0

    def wait(self, timeout):
        self.wait_calls += 1
        return True


class Mission24DSymbolSanitizationTests(unittest.TestCase):
    def setUp(self):
        for symbol in ("=1D", "=1D&LIMIT=8", "INTERVAL=1D", "LIMIT=8", "PETR4", "VALE3", "BTCUSD", "TSLA"):
            clear_symbol_cooldown(symbol)
        market_data_loader._SYMBOL_FAILURES.clear()
        quote_warmup._quote_cooldowns.clear()
        quote_warmup._chart_cooldowns.clear()

    def test_symbol_sanitizer_rejects_query_strings_before_provider(self):
        self.assertIsNone(sanitize_market_symbol("=1D"))
        self.assertIsNone(sanitize_market_symbol("=1D&LIMIT=8"))
        self.assertIsNone(sanitize_market_symbol("interval=1D"))
        self.assertIsNone(sanitize_market_symbol("limit=8"))
        self.assertIsNone(sanitize_market_symbol("?symbol=PETR4"))

    def test_symbol_sanitizer_accepts_valid_symbols(self):
        self.assertEqual(sanitize_market_symbol("PETR4"), "PETR4")
        self.assertEqual(sanitize_market_symbol("VALE3"), "VALE3")
        self.assertEqual(sanitize_market_symbol("BTCUSD"), "BTCUSD")
        self.assertEqual(sanitize_market_symbol("TSLA"), "TSLA")

    def test_market_data_loader_blocks_invalid_symbols_before_yfinance(self):
        with patch.object(market_data_loader, "_get_yfinance", side_effect=AssertionError("provider must not be called")) as yf:
            self.assertIsNone(market_data_loader.batch_download(["=1D"], period="1d", interval="5m"))
            self.assertIsNone(market_data_loader.get_price_snapshot("=1D&LIMIT=8"))
            self.assertEqual(market_data_loader.get_chart_data("interval=1D"), [])

        yf.assert_not_called()
        self.assertTrue(is_symbol_on_cooldown("=1D"))
        self.assertTrue(is_symbol_on_cooldown("=1D&LIMIT=8"))
        self.assertTrue(is_symbol_on_cooldown("interval=1D"))

    def test_market_data_cache_filters_query_params_before_download(self):
        with patch.object(market_data_cache_module, "fetch_market_data", side_effect=AssertionError("provider must not be called")):
            self.assertIsNone(market_data_cache_module.get_market_data(["interval=1D", "limit=8"]))

    def test_warmups_filter_invalid_symbols_before_provider_calls(self):
        with patch.object(quote_warmup, "get_price_snapshots", return_value={"PETR4": {"price": 40.0}}) as get_prices:
            stats = quote_warmup.warm_quotes_once(symbols=["=1D", "=1D&LIMIT=8", "PETR4"], chunk_size=1)

        get_prices.assert_called_once_with(["PETR4"], force_refresh=True)
        self.assertEqual(stats["requested"], 1)

        with patch.object(chart_warmup, "_write_requests") as write_chart:
            chart_warmup.request_chart_warmup("=1D&LIMIT=8", interval="1D")
        write_chart.assert_not_called()

        with patch.object(news_warmup, "_write_requests") as write_news:
            news_warmup.request_news_warmup("limit=8", limit=6)
        write_news.assert_not_called()

    def test_invalid_ticker_enters_cooldown(self):
        self.assertIsNone(market_data_loader.get_price_snapshot("=1D"))
        self.assertTrue(is_symbol_on_cooldown("=1D"))

    def test_worker_does_not_crash_when_engine_returns_invalid_symbol(self):
        invalid_signal = {"ticker": "=1D", "symbol": "=1D", "score": 99, "signal": "BUY"}
        snapshot_payload = {
            "signals": [],
            "source": "empty",
            "stale": True,
            "snapshot_runtime_status": SNAPSHOT_RUNTIME_CRITICAL,
            "snapshot_runtime": {"status": SNAPSHOT_RUNTIME_CRITICAL, "signals": 0, "fallback_active": False},
            "go_live_ready": False,
        }
        with patch.object(worker, "safe_run_engine", return_value=[invalid_signal]), patch.object(
            worker, "generate_market_snapshot", return_value=snapshot_payload
        ) as generate, patch.object(worker, "_prewarm_public_quotes"), patch.object(
            worker, "_prewarm_public_charts"
        ), patch.object(worker, "_prewarm_public_news"), patch.object(worker, "set_workers"):
            worker.worker_loop(SingleCycleStopEvent())

        generate.assert_called_once()

    def test_snapshot_runtime_and_go_live_flags_are_strict(self):
        empty = attach_snapshot_runtime_status({"signals": [], "source": "empty", "stale": True})
        valid = attach_snapshot_runtime_status(
            {
                "signals": [{"ticker": "PETR4", "price": 40.0, "volume": 1_000_000}],
                "source": "engine",
                "stale": False,
                "timestamp": time.time(),
            }
        )

        self.assertEqual(empty["snapshot_runtime_status"], SNAPSHOT_RUNTIME_CRITICAL)
        self.assertFalse(empty["go_live_ready"])
        self.assertEqual(valid["snapshot_runtime_status"], SNAPSHOT_RUNTIME_HEALTHY)
        self.assertTrue(valid["go_live_ready"])


if __name__ == "__main__":
    unittest.main()
