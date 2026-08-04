"""G2 Residue Verification Test

Revalidates commit 5178692e (fix(news): move refresh fetches off request path)
for any remaining issues:
- G2-R1: Atomic check/reserve under lock (concurrency control).
- G2-R2: Real shutdown cleanup.
- G2-R5: Preserve cooldown rules, empty cache handling, error retries.
"""

import time
import threading
from unittest.mock import patch
import pytest

from app.system.news_warmup import (
    request_news_warmup,
    _warm_single_request,
    _graceful_shutdown,
    warm_news_once,
    _lock,
    _async_running,
    _symbol_cooldowns,
    _async_last_request_at,
)
import app.system.news_warmup as news_warmup_module


class TestG2ResidueVerification:
    """G2: Verify news warmup lifecycle fixes are complete against actual news_warmup implementation."""

    def setup_method(self):
        with _lock:
            _async_running.clear()
            _symbol_cooldowns.clear()
            _async_last_request_at.clear()
            news_warmup_module._shutdown_requested = False

    def teardown_method(self):
        with _lock:
            _async_running.clear()
            _symbol_cooldowns.clear()
            _async_last_request_at.clear()
            news_warmup_module._shutdown_requested = False

    def test_news_warmup_atomic_check_and_reserve_under_lock(self):
        """Prove single reservation for same ticker with controlled concurrency."""
        started_count = 0
        started_threads = []

        class MockThread:
            def __init__(self, target, args, name, daemon):
                self.target = target
                self.args = args
                self.name = name

            def start(self):
                nonlocal started_count
                started_count += 1
                started_threads.append(self)

        with patch("app.system.news_warmup.Thread", MockThread):
            def worker():
                request_news_warmup("VALE3", 5, "pt-BR")

            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            with _lock:
                assert len(_async_running) == 1
                assert any(k.startswith("VALE3:") for k in _async_running)
                assert started_count == 1

        class FailingThread:
            def __init__(self, *args, **kwargs):
                pass
            def start(self):
                raise RuntimeError("Cannot start thread")

        with patch("app.system.news_warmup.Thread", FailingThread):
            res = request_news_warmup("MGLU3", 5, "pt-BR")
            assert res is False
            with _lock:
                assert not any(k.startswith("MGLU3:") for k in _async_running)

    def test_news_warmup_lifecycle_atexit_shutdown(self):
        """Prove actual cleanup and idempotency of shutdown."""
        with _lock:
            _async_running.add("FAKE:pt-br")
            news_warmup_module._shutdown_requested = False
        
        def simulate_finish():
            time.sleep(0.1)
            with _lock:
                _async_running.discard("FAKE:pt-br")
                
        threading.Thread(target=simulate_finish).start()

        start_time = time.time()
        _graceful_shutdown()
        elapsed = time.time() - start_time
        
        assert elapsed >= 0.1
        with _lock:
            assert len(_async_running) == 0
            assert news_warmup_module._shutdown_requested is True

    def test_async_path_allows_immediate_retry_on_provider_exception(self):
        """G2-R5: Async path doesn't mark cooldown on provider exception."""
        with patch("app.system.news_warmup.get_cached_symbol_news", return_value=[]):
            with patch("app.system.news_warmup.get_symbol_news", side_effect=Exception("Provider error")):
                _warm_single_request("PETR4", 5, "pt-br", "PETR4:pt-br")

        with _lock:
            assert "PETR4" not in _symbol_cooldowns
            assert "PETR4:pt-br" not in _async_last_request_at

    def test_sync_path_allows_immediate_retry_on_provider_exception(self):
        """G2-R5: Sync path doesn't mark cooldown on provider exception."""
        with patch("app.system.news_warmup._requested_symbols", return_value=[("VALE3", 5, "pt-br")]):
            with patch("app.system.news_warmup.get_cached_symbol_news", return_value=[]):
                with patch("app.system.news_warmup.get_symbol_news", side_effect=Exception("Provider error")):
                    warm_news_once(limit=10, max_calls=1)

        with _lock:
            assert "VALE3" not in _symbol_cooldowns

    def test_news_warmup_cooldown_symmetry(self):
        """Cooldown behavior is symmetric - set on empty result, NOT on exception."""
        with patch("app.system.news_warmup.get_cached_symbol_news", return_value=[]):
            with patch("app.system.news_warmup.get_symbol_news", return_value=[]):
                _warm_single_request("ITUB4", 5, "pt-br", "ITUB4:pt-br")

        with _lock:
            assert "ITUB4" in _symbol_cooldowns

        with _lock:
            _symbol_cooldowns.pop("SANB11", None)

        with patch("app.system.news_warmup.get_cached_symbol_news", return_value=[]):
            with patch("app.system.news_warmup.get_symbol_news", side_effect=Exception("Error")):
                _warm_single_request("SANB11", 5, "pt-br", "SANB11:pt-br")

        with _lock:
            assert "SANB11" not in _symbol_cooldowns



if __name__ == "__main__":
    pytest.main([__file__, "-v"])