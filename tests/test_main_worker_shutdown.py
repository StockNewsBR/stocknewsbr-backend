"""Background worker shutdown contract for the FastAPI lifespan.

The lifespan starts daemon threads (engine worker, referral worker, AI worker)
and, on shutdown, only used to call ``STOP_EVENT.set()``. It never joined them
and never cleared ``BACKGROUND_THREADS``, which leaves two real defects:

1. Shutdown returns while workers are still mid-iteration, so a worker can be
   holding a DB session when the process tears down.
2. The next startup calls ``STOP_EVENT.clear()``. A worker from the previous
   cycle that had not yet observed the ``set()`` sees the flag cleared again and
   keeps running forever — leaked, unowned, and invisible to ``_start_thread``
   (which only skips creation while the stale thread is alive).

These tests pin the contract: signal, join, and clear the registry.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

import main


@pytest.fixture(autouse=True)
def _clean_thread_registry():
    """Isolate the module-level worker registry around every test."""
    main.STOP_EVENT.clear()
    with main.THREAD_LOCK:
        main.BACKGROUND_THREADS.clear()

    yield

    main.STOP_EVENT.set()
    with main.THREAD_LOCK:
        threads = list(main.BACKGROUND_THREADS.values())
        main.BACKGROUND_THREADS.clear()
    for thread in threads:
        if thread.is_alive():
            thread.join(timeout=5)
    main.STOP_EVENT.clear()
    main.WORKERS_STARTED = False


def _cooperative_worker(stop_event: threading.Event) -> None:
    """Mirror the real workers: loop until signalled, sleeping on the event."""
    while not stop_event.is_set():
        stop_event.wait(0.02)


class TestStopBackgroundThreads:
    def test_joins_running_threads_and_clears_registry(self):
        assert main._start_thread("test-shutdown-worker", _cooperative_worker, main.STOP_EVENT)
        thread = main.BACKGROUND_THREADS["test-shutdown-worker"]
        assert thread.is_alive()

        stragglers = main._stop_background_threads(timeout=5.0)

        assert stragglers == []
        assert not thread.is_alive(), "worker must be joined, not merely signalled"
        assert main.BACKGROUND_THREADS == {}

    def test_reports_threads_that_refuse_to_exit(self):
        """A wedged worker must be reported, never silently ignored."""
        release = threading.Event()

        def wedged(stop_event: threading.Event) -> None:
            del stop_event
            release.wait(30)

        try:
            assert main._start_thread("test-wedged-worker", wedged, main.STOP_EVENT)
            stragglers = main._stop_background_threads(timeout=0.2)
            assert stragglers == ["test-wedged-worker"]
        finally:
            release.set()

    def test_is_safe_with_no_threads_registered(self):
        assert main._stop_background_threads(timeout=1.0) == []
        assert main.BACKGROUND_THREADS == {}


class TestLifespanShutdown:
    def test_lifespan_joins_workers_before_returning(self, monkeypatch):
        """End-to-end: after the lifespan exits, no worker thread survives."""
        monkeypatch.setattr(main, "validate_runtime_security_settings", lambda: None)
        monkeypatch.setattr(main, "validate_database_configuration", lambda **_: None)
        monkeypatch.setattr(main, "_create_tables_if_needed", lambda: None)
        monkeypatch.setattr(main, "_seed_official_identities_if_needed", lambda: None)
        # Keep the referral loop pure in-memory: no DB, no network.
        monkeypatch.setattr(main, "validate_referrals", lambda _db: None)
        monkeypatch.setattr(main, "SessionLocal", lambda: _NullSession())

        monkeypatch.setenv("START_ENGINE_WORKER", "0")
        monkeypatch.setenv("START_AI_WORKER", "0")
        monkeypatch.setenv("START_SNAPSHOT_WORKER", "0")
        monkeypatch.setenv("START_QUOTE_WARMUP", "0")
        monkeypatch.setenv("START_REFERRAL_WORKER", "1")

        main.WORKERS_STARTED = False

        async def _run():
            async with main.lifespan(main.app):
                with main.THREAD_LOCK:
                    started = dict(main.BACKGROUND_THREADS)
                assert "stocknewsbr-referral-worker" in started
                assert started["stocknewsbr-referral-worker"].is_alive()
                return started

        started = asyncio.run(_run())

        for name, thread in started.items():
            assert not thread.is_alive(), f"{name} survived lifespan shutdown"
        assert main.BACKGROUND_THREADS == {}
        assert main.WORKERS_STARTED is False

    def test_next_startup_cannot_resurrect_a_previous_worker(self, monkeypatch):
        """STOP_EVENT.clear() on restart must not revive last cycle's thread."""
        monkeypatch.setattr(main, "validate_runtime_security_settings", lambda: None)
        monkeypatch.setattr(main, "validate_database_configuration", lambda **_: None)
        monkeypatch.setattr(main, "_create_tables_if_needed", lambda: None)
        monkeypatch.setattr(main, "_seed_official_identities_if_needed", lambda: None)
        monkeypatch.setattr(main, "validate_referrals", lambda _db: None)
        monkeypatch.setattr(main, "SessionLocal", lambda: _NullSession())

        monkeypatch.setenv("START_ENGINE_WORKER", "0")
        monkeypatch.setenv("START_AI_WORKER", "0")
        monkeypatch.setenv("START_SNAPSHOT_WORKER", "0")
        monkeypatch.setenv("START_QUOTE_WARMUP", "0")
        monkeypatch.setenv("START_REFERRAL_WORKER", "1")

        main.WORKERS_STARTED = False

        async def _cycle():
            async with main.lifespan(main.app):
                with main.THREAD_LOCK:
                    return main.BACKGROUND_THREADS["stocknewsbr-referral-worker"]

        first = asyncio.run(_cycle())
        assert not first.is_alive()

        second = asyncio.run(_cycle())
        assert second is not first, "restart must own a fresh thread"
        assert not second.is_alive()


class TestConclusionExecutorShutdown:
    """The LLM conclusion pool must be released with the application.

    ``shutdown_executor`` is documented as safe for application shutdown and is
    idempotent (the next request lazily rebuilds the pool), but nothing outside
    the test-suite ever called it. The pool is created on the first bundle
    request and its queue can hold a backlog of 20-second provider calls, so a
    shutdown that skips it leaves that backlog running against a process that
    is supposed to be going away.
    """

    def _neutralize_bootstrap(self, monkeypatch):
        monkeypatch.setattr(main, "validate_runtime_security_settings", lambda: None)
        monkeypatch.setattr(main, "validate_database_configuration", lambda **_: None)
        monkeypatch.setattr(main, "_create_tables_if_needed", lambda: None)
        monkeypatch.setattr(main, "_seed_official_identities_if_needed", lambda: None)
        for flag in (
            "START_ENGINE_WORKER",
            "START_AI_WORKER",
            "START_SNAPSHOT_WORKER",
            "START_QUOTE_WARMUP",
            "START_REFERRAL_WORKER",
        ):
            monkeypatch.setenv(flag, "0")
        main.WORKERS_STARTED = False

    def test_lifespan_releases_the_conclusion_pool(self, monkeypatch):
        from app.ai import conclusion_generator

        self._neutralize_bootstrap(monkeypatch)

        conclusion_generator._get_executor()
        assert conclusion_generator._EXECUTOR is not None

        async def _run():
            async with main.lifespan(main.app):
                pass

        try:
            asyncio.run(_run())
            assert conclusion_generator._EXECUTOR is None, (
                "conclusion executor survived application shutdown"
            )
        finally:
            conclusion_generator.shutdown_executor(wait=True)

    def test_shutdown_is_safe_when_the_pool_was_never_created(self, monkeypatch):
        from app.ai import conclusion_generator

        self._neutralize_bootstrap(monkeypatch)
        conclusion_generator.shutdown_executor(wait=True)
        assert conclusion_generator._EXECUTOR is None

        async def _run():
            async with main.lifespan(main.app):
                pass

        asyncio.run(_run())
        assert conclusion_generator._EXECUTOR is None


class _NullSession:
    """Minimal stand-in so the referral worker never touches a real database."""

    def close(self) -> None:
        return None

    def rollback(self) -> None:
        return None
