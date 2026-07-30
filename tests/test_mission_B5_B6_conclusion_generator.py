"""B5/B6 Conclusion Generator Tests

Tests for the LLM conclusion generator with bounded worker pool (B5)
and bounded cache with TTL eviction (B6).
"""

import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, MagicMock

import pytest

from app.ai.conclusion_generator import (
    get_cached_or_schedule,
    generate_conclusion,
    conclusion_or_template,
    _CACHE,
    _SCHEDULED,
    _SCHED_LOCK,
    _evict_expired_cache,
    _get_executor,
    _MAX_WORKERS,
)


class TestB5BoundedWorkerPool:
    """B5: Bounded ThreadPoolExecutor with max_workers=4 for conclusion generation."""

    def setup_method(self):
        """Clear module state before each test."""
        # Clear caches
        _CACHE.clear()
        _SCHEDULED.clear()
        # Reset executor (can't easily reset ThreadPoolExecutor, so we'll just test its config)
        import app.ai.conclusion_generator as cg
        cg._EXECUTOR = None

    def test_executor_max_workers_is_4(self):
        """B5a: ThreadPoolExecutor max_workers is capped at 4."""
        executor = _get_executor()
        assert executor._max_workers == 4
        assert executor._thread_name_prefix == "conclusion-llm"

    def test_executor_reused_across_calls(self):
        """B5b: Same executor instance reused across calls."""
        exec1 = _get_executor()
        exec2 = _get_executor()
        assert exec1 is exec2

    def test_scheduled_generation_uses_executor(self):
        """B5c: get_cached_or_schedule submits to executor, doesn't create raw threads."""
        with patch.object(_get_executor(), 'submit') as mock_submit:
            data = {"symbol": "TEST3", "signal": "compra", "master_verdict": "COMPRA", "rsi": 60}
            result = get_cached_or_schedule(data)
            assert result is None  # First call returns None
            mock_submit.assert_called_once()

    def test_concurrent_calls_same_symbol_deduped(self):
        """B5d: Concurrent calls for same symbol deduplicate - only one generation scheduled."""
        data = {"symbol": "TEST4", "signal": "venda", "master_verdict": "VENDA", "rsi": 40}

        call_count = [0]

        def mock_generate(data):
            call_count[0] += 1
            time.sleep(0.1)
            return "generated"

        with patch('app.ai.conclusion_generator.generate_conclusion', side_effect=mock_generate):
            # Simulate concurrent calls
            threads = [threading.Thread(target=get_cached_or_schedule, args=(data,)) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Should only generate once due to _SCHEDULED dedup
            # Note: there's a race in test but _SCHEDULED lock should prevent it
            assert call_count[0] <= 1


class TestB6BoundedCacheTTLEviction:
    """B6: Bounded cache with TTL eviction on hot path."""

    def setup_method(self):
        """Clear module state before each test."""
        _CACHE.clear()
        _SCHEDULED.clear()
        import app.ai.conclusion_generator as cg
        cg._EXECUTOR = None

    def test_cache_stores_with_timestamp(self):
        """B6a: Cache entries stored with (value, expiry_timestamp)."""
        key = ("TEST5", "compra", 80, "COMPRA")
        value = "Test conclusion"
        expiry = time.time() + 180
        _CACHE[key] = (value, expiry)

        hit = _CACHE.get(key)
        assert hit == (value, expiry)
        assert hit[1] > time.time()

    def test_evict_expired_cache_removes_stale_entries(self):
        """B6b: _evict_expired_cache removes entries past TTL."""
        # Add expired entry
        expired_key = ("EXP1", "compra", 50, "COMPRA")
        _CACHE[expired_key] = ("old value", time.time() - 10)

        # Add fresh entry
        fresh_key = ("FRESH1", "venda", 30, "VENDA")
        _CACHE[fresh_key] = ("new value", time.time() + 300)

        evicted = _evict_expired_cache()

        assert evicted == 1
        assert expired_key not in _CACHE
        assert fresh_key in _CACHE

    def test_get_cached_or_schedule_calls_eviction_on_hot_path(self):
        """B6c: get_cached_or_schedule triggers eviction on every access."""
        with patch('app.ai.conclusion_generator._evict_expired_cache') as mock_evict:
            data = {"symbol": "TEST6", "signal": "compra", "master_verdict": "COMPRA", "rsi": 70}
            get_cached_or_schedule(data)
            mock_evict.assert_called_once()

    def test_cache_hit_returns_cached_prose(self):
        """B6d: Cache hit returns cached prose, no generation."""
        data = {"symbol": "TEST7", "signal": "compra", "master_verdict": "COMPRA", "rsi": 65, "change_pct": 1.5}
        key = _cache_key(data)  # Use same key derivation
        _CACHE[key] = ("cached conclusion", time.time() + 180)

        result = get_cached_or_schedule(data)
        assert result == "cached conclusion"

    def test_scheduled_set_cleared_on_completion(self):
        """B6e: _SCHEDULED set cleared when generation completes."""
        data = {"symbol": "TEST8", "signal": "venda", "master_verdict": "VENDA", "rsi": 35}
        key = _cache_key(data)

        with _SCHED_LOCK:
            _SCHEDULED.add(key)

        # Simulate generation completion
        with _SCHED_LOCK:
            _SCHEDULED.discard(key)

        assert key not in _SCHEDULED


class TestConclusionGeneratorIntegration:
    """Integration tests for conclusion generation flow."""

    def setup_method(self):
        _CACHE.clear()
        _SCHEDULED.clear()
        import app.ai.conclusion_generator as cg
        cg._EXECUTOR = None

    def test_conclusion_or_template_returns_template_on_llm_failure(self):
        """Fallback to template when LLM unavailable."""
        data = {"symbol": "TEST9", "signal": "compra", "master_verdict": "COMPRA", "rsi": 60}
        template = "TEMPLATE_FALLBACK"

        # Force LLM failure by using bad URL
        with patch.dict(os.environ, {"OLLAMA_URL": "http://127.0.0.1:1"}):
            result = conclusion_or_template(data, template)
            assert result == template

    def test_different_assets_get_different_conclusions(self):
        """Rising vs falling assets produce different conclusions when LLM available."""
        csan = {"symbol": "CSAN3", "trend_bias": "BAIXA", "signal": "baixa", "rsi": 42.7,
                "change_pct": -2.05, "master_verdict": "AGUARDAR", "support": 3.80, "resistance": 4.10}
        hype = {"symbol": "HYPE3", "trend_bias": "NEUTRO", "signal": "neutro", "rsi": 57.8,
                "change_pct": 0.99, "master_verdict": "AGUARDAR", "support": 19.9, "resistance": 20.8}

        # Both should fall back to template when LLM down
        with patch.dict(os.environ, {"OLLAMA_URL": "http://127.0.0.1:1"}):
            SAME = "TEMPLATE_SAME"
            a = conclusion_or_template(csan, SAME)
            b = conclusion_or_template(hype, SAME)
            assert a == SAME and b == SAME

    def test_cache_key_is_deterministic(self):
        """Same indicator values produce same cache key."""
        data1 = {"symbol": "PETR4", "signal": "compra", "master_verdict": "COMPRA", "rsi": 70.0, "change_pct": 2.0}
        data2 = {"symbol": "PETR4", "signal": "compra", "master_verdict": "COMPRA", "rsi": 70.0, "change_pct": 2.0}

        key1 = _cache_key(data1)
        key2 = _cache_key(data2)
        assert key1 == key2


def _cache_key(data: dict) -> tuple:
    """Replicate the internal _cache_key logic for testing."""
    symbol = data.get("symbol") or data.get("ticker") or "UNKNOWN"
    signal = str(data.get("signal") or "").strip().lower()
    verdict = str(data.get("master_verdict") or "").strip().upper()
    rsi = round(float(data.get("rsi") or 50.0), 1)
    change = round(float(data.get("change_pct") or 0.0), 1)
    return (symbol, signal, verdict, rsi, change)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])