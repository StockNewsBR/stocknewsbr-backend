"""B5/B6 Conclusion Generator Tests

B5 -- bounded worker pool: one global executor, max_workers respected, dedup by key,
backpressure, reservation released on every failure path, graceful shutdown, and no raw
thread per request.

B6 -- bounded cache: TTL eviction, opportunistic cleanup, maxsize, thread safety.

No test here may reach the network. `_no_real_network` replaces the transport with a
tripwire, so a green run is itself the proof that zero provider calls were made.
"""

import threading
import time
from unittest.mock import patch

import pytest

import app.ai.conclusion_generator as cg
from app.ai.conclusion_generator import (
    _CACHE,
    _EVICT_INTERVAL,
    _MAX_CACHE_ENTRIES,
    _MAX_PENDING,
    _MAX_WORKERS,
    _SCHED_LOCK,
    _SCHEDULED,
    _cache_key,
    _cache_put,
    _evict_expired_cache,
    _get_executor,
    conclusion_or_template,
    generate_conclusion,
    get_cached_or_schedule,
    shutdown_executor,
)


class RealNetworkAttempted(BaseException):
    """Raised when a test would have hit a real provider.

    Deliberately NOT an Exception subclass: `_call_ollama` / `_call_omniroute` wrap their
    transport in `except Exception -> return None`, which would silently swallow the
    tripwire and let the test pass while actually calling Ollama or OmniRoute.
    """


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """Fail loudly on any real provider call.

    The module binds _OLLAMA_URL / _OMNI_URL at import time, so patching os.environ has
    no effect whatsoever -- the transport itself is the only reliable guard.
    """

    def _blocked(url, *args, **kwargs):
        raise RealNetworkAttempted(f"real network call attempted: {url}")

    monkeypatch.setattr(cg.requests, "post", _blocked)


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Isolate module globals and never leak pool threads between tests."""
    shutdown_executor(wait=True)
    _CACHE.clear()
    _SCHEDULED.clear()
    cg._last_evict_at = 0.0
    yield
    shutdown_executor(wait=True)
    _CACHE.clear()
    _SCHEDULED.clear()
    cg._last_evict_at = 0.0


def _asset(symbol: str, **overrides) -> dict:
    data = {
        "symbol": symbol,
        "signal": "compra",
        "master_verdict": "COMPRA",
        "rsi": 60.0,
        "change_pct": 1.0,
    }
    data.update(overrides)
    return data


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class TestNetworkGuard:
    def test_guard_is_armed(self):
        """A real transport call fails the test instead of reaching a provider."""
        with pytest.raises(RealNetworkAttempted):
            cg.requests.post("http://127.0.0.1:11434/api/generate", json={})

    def test_guard_survives_the_modules_broad_except(self):
        """_call_ollama's `except Exception` must not swallow the tripwire."""
        with pytest.raises(RealNetworkAttempted):
            cg._call_ollama("prompt")


class TestB5BoundedWorkerPool:
    """B5: one bounded global pool instead of a thread per request."""

    def test_executor_is_bounded_and_named(self):
        executor = _get_executor()
        assert executor._max_workers == _MAX_WORKERS
        assert _MAX_WORKERS == 4  # default; CONCLUSION_LLM_MAX_WORKERS tunes it
        assert executor._thread_name_prefix == "conclusion-llm"

    def test_executor_reused_across_calls(self):
        assert _get_executor() is _get_executor()

    def test_scheduled_generation_uses_executor(self):
        """Work is submitted to the pool, never to a fresh Thread."""
        with patch.object(_get_executor(), "submit") as mock_submit:
            assert get_cached_or_schedule(_asset("TEST3")) is None
            mock_submit.assert_called_once()

    def test_live_threads_never_exceed_max_workers(self):
        """B5 core: N distinct symbols must not produce N threads."""
        release = threading.Event()
        lock = threading.Lock()
        active = [0]
        peak = [0]

        def _blocking_llm(prompt):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            release.wait(5)
            with lock:
                active[0] -= 1
            return "conclusao"

        try:
            with patch.object(cg, "_call_llm", side_effect=_blocking_llm):
                for i in range(_MAX_WORKERS * 3):
                    get_cached_or_schedule(_asset(f"SYM{i}", rsi=50.0 + i))

                assert _wait_until(lambda: peak[0] >= _MAX_WORKERS)
                pool_threads = [
                    t for t in threading.enumerate()
                    if t.name.startswith("conclusion-llm")
                ]
                assert len(pool_threads) <= _MAX_WORKERS
                release.set()
                shutdown_executor(wait=True, cancel_futures=False)
        finally:
            release.set()

        assert peak[0] <= _MAX_WORKERS

    def test_concurrent_calls_same_symbol_generate_once(self):
        """B5 dedup: 5 concurrent refreshes of one symbol = exactly 1 provider call."""
        data = _asset("TEST4", signal="venda", master_verdict="VENDA", rsi=40.0)
        release = threading.Event()
        lock = threading.Lock()
        calls = []

        def _blocking_llm(prompt):
            with lock:
                calls.append(prompt)
            release.wait(5)
            return "generated"

        try:
            with patch.object(cg, "_call_llm", side_effect=_blocking_llm):
                threads = [
                    threading.Thread(target=get_cached_or_schedule, args=(data,))
                    for _ in range(5)
                ]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()

                # Exactly one reservation, regardless of pool progress.
                assert len(_SCHEDULED) == 1
                release.set()
                shutdown_executor(wait=True, cancel_futures=False)
        finally:
            release.set()

        assert len(calls) == 1

    def test_repeated_requests_same_key_submit_once(self):
        """B5 dedup: a second refresh while the first is in flight submits nothing."""
        data = _asset("REPEAT3", rsi=52.0)

        with patch.object(_get_executor(), "submit") as mock_submit:
            assert get_cached_or_schedule(data) is None
            assert get_cached_or_schedule(data) is None
            assert get_cached_or_schedule(dict(data)) is None  # equal payload, new dict
            mock_submit.assert_called_once()

        assert _SCHEDULED == {_cache_key(data)}

    def test_backpressure_drops_when_backlog_is_full(self):
        """B5: past _MAX_PENDING the refresh is dropped, never queued unboundedly."""
        with _SCHED_LOCK:
            for i in range(_MAX_PENDING):
                _SCHEDULED.add((f"FILLER{i}", "", "", 0.0, 0.0))

        data = _asset("OVERFLOW3", rsi=55.0)
        with patch.object(_get_executor(), "submit") as mock_submit:
            assert get_cached_or_schedule(data) is None
            mock_submit.assert_not_called()

        assert _cache_key(data) not in _SCHEDULED

    def test_provider_exception_releases_reservation(self):
        """B5: an exploding provider must not strand the key."""
        data = _asset("BOOM3", rsi=61.0)
        with patch.object(cg, "_call_llm", side_effect=RuntimeError("provider exploded")):
            assert get_cached_or_schedule(data) is None
            # Released by _fill()'s finally -- asserted before any shutdown runs.
            assert _wait_until(lambda: _cache_key(data) not in _SCHEDULED)

    def test_submit_failure_releases_reservation(self):
        """B5 regression: a failing submit() must not block the symbol forever."""
        data = _asset("NOSUBMIT3", rsi=58.0)

        with patch.object(_get_executor(), "submit", side_effect=RuntimeError("pool down")):
            assert get_cached_or_schedule(data) is None

        assert _cache_key(data) not in _SCHEDULED

        # The symbol must still be schedulable afterwards.
        with patch.object(_get_executor(), "submit") as retry_submit:
            assert get_cached_or_schedule(data) is None
            retry_submit.assert_called_once()

    def test_shutdown_is_graceful_and_idempotent(self):
        """B5: shutdown drops the pool, clears reservations, and can be repeated."""
        with _SCHED_LOCK:
            _SCHEDULED.add(("STUCK3", "", "", 0.0, 0.0))
        _get_executor()
        assert cg._EXECUTOR is not None

        shutdown_executor(wait=True)
        assert cg._EXECUTOR is None
        assert _SCHEDULED == set()

        shutdown_executor(wait=True)  # idempotent
        assert _get_executor() is not None  # lazily rebuilt


class TestB6BoundedCacheTTLEviction:
    """B6: bounded cache with TTL eviction on the hot path."""

    def test_cache_stores_value_with_expiry(self):
        key = _cache_key(_asset("TEST5"))
        expiry = time.time() + 180
        _CACHE[key] = ("Test conclusion", expiry)

        assert _CACHE.get(key) == ("Test conclusion", expiry)

    def test_evict_expired_cache_removes_stale_entries(self):
        expired_key = _cache_key(_asset("EXP1"))
        _CACHE[expired_key] = ("old value", time.time() - 10)
        fresh_key = _cache_key(_asset("FRESH1", signal="venda", master_verdict="VENDA"))
        _CACHE[fresh_key] = ("new value", time.time() + 300)

        assert _evict_expired_cache() == 1
        assert expired_key not in _CACHE
        assert fresh_key in _CACHE

    def test_get_cached_or_schedule_triggers_eviction(self):
        with patch.object(_get_executor(), "submit"), \
                patch.object(cg, "_evict_expired_cache") as mock_evict:
            get_cached_or_schedule(_asset("TEST6", rsi=70.0))
            mock_evict.assert_called_once()

    def test_cache_hit_returns_cached_prose(self):
        data = _asset("TEST7", rsi=65.0, change_pct=1.5)
        _CACHE[_cache_key(data)] = ("cached conclusion", time.time() + 180)

        assert get_cached_or_schedule(data) == "cached conclusion"

    def test_expired_cache_hit_is_not_served(self):
        data = _asset("TEST7B", rsi=66.0)
        _CACHE[_cache_key(data)] = ("stale conclusion", time.time() - 1)

        with patch.object(_get_executor(), "submit"):
            assert get_cached_or_schedule(data) is None

    def test_thousands_of_expired_entries_are_evicted(self):
        """B6: a long-lived process must not accumulate dead keys."""
        expired = time.time() - 1
        fresh_until = time.time() + 300
        for i in range(5000):
            _CACHE[(f"DEAD{i}", "compra", "COMPRA", 50.0, 1.0)] = ("old", expired)
        fresh = {(f"LIVE{i}", "venda", "VENDA", 30.0, -1.0) for i in range(10)}
        for key in fresh:
            _CACHE[key] = ("new", fresh_until)

        assert _evict_expired_cache() == 5000
        assert set(_CACHE) == fresh

    def test_maxsize_caps_the_cache(self):
        """B6: TTL alone does not bound memory -- the ceiling does."""
        for i in range(_MAX_CACHE_ENTRIES + 200):
            _cache_put((f"BULK{i}", "compra", "COMPRA", 50.0, 1.0), "prose")

        assert len(_CACHE) <= _MAX_CACHE_ENTRIES

    def test_maxsize_drops_soonest_to_expire_first(self):
        """B6: the ceiling must not evict entries that still have the most life left."""
        now = time.time()
        doomed = ("DOOMED3", "compra", "COMPRA", 50.0, 1.0)
        for i in range(_MAX_CACHE_ENTRIES - 1):
            _CACHE[(f"KEEP{i}", "compra", "COMPRA", 50.0, 1.0)] = ("prose", now + 9000)
        _CACHE[doomed] = ("about to die", now + 1)

        _cache_put(("NEWEST3", "compra", "COMPRA", 50.0, 1.0), "prose", now=now)

        assert len(_CACHE) == _MAX_CACHE_ENTRIES
        assert doomed not in _CACHE
        assert ("NEWEST3", "compra", "COMPRA", 50.0, 1.0) in _CACHE

    def test_generate_conclusion_respects_the_ceiling(self):
        with patch.object(cg, "_call_llm", return_value="prose"):
            for i in range(_MAX_CACHE_ENTRIES + 20):
                generate_conclusion(_asset(f"GEN{i}", rsi=40.0 + (i % 50)))

        assert len(_CACHE) <= _MAX_CACHE_ENTRIES

    def test_opportunistic_cleanup_is_throttled_on_hot_path(self):
        """B6: the request path must not pay an O(n) sweep every time."""
        data = _asset("THROTTLE3", rsi=44.0)
        key = _cache_key(data)
        _CACHE[key] = ("stale prose", time.time() - 1)
        cg._last_evict_at = time.time()  # pretend a sweep just ran

        with patch.object(_get_executor(), "submit"):
            assert get_cached_or_schedule(data) is None  # expired entry never served

        assert key in _CACHE  # sweep was skipped ...
        assert _evict_expired_cache() == 1  # ... but a forced sweep still collects it

    def test_sweep_resumes_after_the_interval(self):
        data = _asset("THROTTLE4", rsi=45.0)
        key = _cache_key(data)
        _CACHE[key] = ("stale prose", time.time() - 1)
        cg._last_evict_at = time.time() - _EVICT_INTERVAL - 1  # window elapsed

        with patch.object(_get_executor(), "submit"):
            get_cached_or_schedule(data)

        assert key not in _CACHE

    def test_malformed_payload_does_not_break_the_hot_path(self):
        """A bad rsi must not raise out of the panel's entrypoint."""
        assert get_cached_or_schedule(_asset("BAD3", rsi="not-a-number")) is None


class TestB6CacheThreadSafety:
    """B6 regression: the sweep used to iterate _CACHE while writers mutated it unlocked."""

    def test_concurrent_writes_and_eviction_never_raise(self):
        errors = []
        stop = threading.Event()

        def _writer(offset):
            try:
                i = 0
                while not stop.is_set():
                    _cache_put((f"W{offset}", "compra", "COMPRA", float(i % 100), 1.0), "prose")
                    i += 1
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        def _sweeper():
            try:
                while not stop.is_set():
                    _evict_expired_cache()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=_writer, args=(n,)) for n in range(6)]
        threads += [threading.Thread(target=_sweeper) for _ in range(3)]
        for t in threads:
            t.start()
        time.sleep(0.5)
        stop.set()
        for t in threads:
            t.join(5)

        assert errors == []
        assert len(_CACHE) <= _MAX_CACHE_ENTRIES


class TestConclusionGeneratorIntegration:
    """Fallback contract: the panel never breaks, whatever the provider does."""

    def test_returns_template_when_provider_returns_nothing(self):
        with patch.object(cg, "_call_llm", return_value=None):
            assert conclusion_or_template(_asset("TEST9"), "TEMPLATE") == "TEMPLATE"

    def test_returns_template_when_provider_raises(self):
        with patch.object(cg, "_call_llm", side_effect=RuntimeError("provider down")):
            assert conclusion_or_template(_asset("TEST9B"), "TEMPLATE") == "TEMPLATE"

    def test_different_assets_get_different_conclusions(self):
        """Rising vs falling assets must not share prose."""
        csan = _asset("CSAN3", trend_bias="BAIXA", signal="baixa", rsi=42.7,
                      change_pct=-2.05, master_verdict="AGUARDAR", support=3.80, resistance=4.10)
        hype = _asset("HYPE3", trend_bias="NEUTRO", signal="neutro", rsi=57.8,
                      change_pct=0.99, master_verdict="AGUARDAR", support=19.9, resistance=20.8)

        def _per_symbol(prompt):
            return "Tendencia de baixa." if "CSAN3" in prompt else "Tendencia neutra."

        with patch.object(cg, "_call_llm", side_effect=_per_symbol):
            first = conclusion_or_template(csan, "TEMPLATE")
            second = conclusion_or_template(hype, "TEMPLATE")

        assert first != second
        assert "TEMPLATE" not in (first, second)

    def test_cache_key_is_deterministic(self):
        assert _cache_key(_asset("PETR4", rsi=70.0, change_pct=2.0)) == _cache_key(
            _asset("PETR4", rsi=70.0, change_pct=2.0)
        )

    def test_cache_key_separates_symbols(self):
        assert _cache_key(_asset("PETR4")) != _cache_key(_asset("VALE3"))
