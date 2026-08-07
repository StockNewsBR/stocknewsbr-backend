"""_RANK_CACHE is shared mutable state reached from concurrent threads.

`GET /ranking` and `GET /ranking/top` are plain `def` handlers, so FastAPI runs
them in its threadpool: several requests touch `_RANK_CACHE` at the same time.
The cache was a bare module-level dict with no synchronization at all, mutated
field by field in four separate places and read field by field in the guard.

Two defects follow.

1. Torn read. The publish sequence is three independent statements:

       _RANK_CACHE["data"] = list(results)          # new rows land first
       _RANK_CACHE["timestamp"] = now
       _RANK_CACHE["snapshot_signature"] = signature

   A reader interleaving after the first statement sees the *new* rows, the
   *old* signature and the *old* timestamp — so the guard passes and it returns
   fresh rows attributed to the previous snapshot. The signature exists
   precisely to bind cached rows to the snapshot they came from, and a torn
   publish defeats it.

2. Cache stampede. Nothing coalesces concurrent misses, so every thread that
   arrives during a refresh recomputes the whole ranking independently.

The fix pairs an atomic publish (all three fields under one lock) with a
separate refresh lock that serializes recomputation. The data lock is never
held across the computation, so this does not trade a stampede for a broad
lock held during I/O.
"""

from __future__ import annotations

import threading
import time

import pytest

from app.services import ranking


@pytest.fixture(autouse=True)
def _reset_cache():
    ranking._RANK_CACHE["data"] = []
    ranking._RANK_CACHE["timestamp"] = 0.0
    ranking._RANK_CACHE["snapshot_signature"] = ""
    yield
    ranking._RANK_CACHE["data"] = []
    ranking._RANK_CACHE["timestamp"] = 0.0
    ranking._RANK_CACHE["snapshot_signature"] = ""


@pytest.fixture
def stub_snapshot(monkeypatch):
    """Deterministic snapshot input, with a counted normalization step."""
    state = {"signature": "sig-1", "calls": 0}

    monkeypatch.setattr(ranking, "get_snapshot_info", lambda: {"stub": True})
    monkeypatch.setattr(ranking, "_snapshot_signature", lambda _info: state["signature"])

    def normalize(_info=None):
        state["calls"] += 1
        time.sleep(0.05)  # widen the window every racing thread must survive
        return [{"ticker": "PETR4", "score": 70}]

    monkeypatch.setattr(ranking, "_normalize_snapshot_ranking", normalize)
    return state


class TestStampede:
    def test_concurrent_misses_recompute_once(self, stub_snapshot):
        results: list[list] = []
        errors: list[BaseException] = []
        barrier = threading.Barrier(8)

        def worker():
            try:
                barrier.wait(timeout=10)
                results.append(ranking.generate_ranking())
            except BaseException as exc:  # noqa: BLE001 -- surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert not errors, f"worker raised: {errors}"
        assert len(results) == 8
        assert stub_snapshot["calls"] == 1, (
            f"cache stampede: {stub_snapshot['calls']} concurrent recomputations"
        )
        for payload in results:
            assert payload == [{"ticker": "PETR4", "score": 70}]

    def test_force_refresh_still_recomputes(self, stub_snapshot):
        ranking.generate_ranking()
        assert stub_snapshot["calls"] == 1

        ranking.generate_ranking(force_refresh=True)
        assert stub_snapshot["calls"] == 2


class TestAtomicPublish:
    def test_cache_exposes_a_lock(self):
        assert hasattr(ranking, "_RANK_CACHE_LOCK"), (
            "_RANK_CACHE is shared across threadpool workers and needs a lock"
        )

    def test_reads_block_while_a_publish_is_in_flight(self, stub_snapshot):
        """A reader must never observe a half-written entry."""
        ranking.generate_ranking()

        observed: list = []
        released = threading.Event()

        def reader():
            observed.append(ranking._read_rank_cache("sig-1", time.time()))
            released.set()

        with ranking._RANK_CACHE_LOCK:
            thread = threading.Thread(target=reader)
            thread.start()
            # While the lock is held the reader cannot make progress.
            assert not released.wait(0.3), "read observed the cache mid-publish"

        thread.join(timeout=5)
        assert released.is_set()
        assert observed == [[{"ticker": "PETR4", "score": 70}]]

    def test_publish_is_all_or_nothing(self, stub_snapshot):
        ranking._write_rank_cache([{"ticker": "VALE3"}], 1234.0, "sig-x")

        assert ranking._RANK_CACHE["data"] == [{"ticker": "VALE3"}]
        assert ranking._RANK_CACHE["timestamp"] == 1234.0
        assert ranking._RANK_CACHE["snapshot_signature"] == "sig-x"

    def test_published_rows_are_copied(self, stub_snapshot):
        rows = [{"ticker": "VALE3"}]
        ranking._write_rank_cache(rows, time.time(), "sig-x")
        rows.append({"ticker": "MUTATED"})

        assert ranking._RANK_CACHE["data"] == [{"ticker": "VALE3"}]


class TestCacheSemanticsPreserved:
    def test_hit_returns_cached_rows_without_recomputing(self, stub_snapshot):
        first = ranking.generate_ranking()
        second = ranking.generate_ranking()

        assert first == second
        assert stub_snapshot["calls"] == 1

    def test_signature_change_invalidates(self, stub_snapshot):
        ranking.generate_ranking()
        assert stub_snapshot["calls"] == 1

        stub_snapshot["signature"] = "sig-2"
        ranking.generate_ranking()
        assert stub_snapshot["calls"] == 2

    def test_expired_entry_invalidates(self, stub_snapshot):
        ranking.generate_ranking()
        assert stub_snapshot["calls"] == 1

        ranking._RANK_CACHE["timestamp"] = time.time() - (ranking.CACHE_TTL + 1)
        ranking.generate_ranking()
        assert stub_snapshot["calls"] == 2

    def test_callers_get_independent_lists(self, stub_snapshot):
        first = ranking.generate_ranking()
        first.append({"ticker": "MUTATED"})

        assert ranking.generate_ranking() == [{"ticker": "PETR4", "score": 70}]
