"""Mission C18 - a snapshot must not move backwards through its own publish path.

`build_snapshot_payload` stamps `generated_at` when it *starts* building, so a
producer that starts earlier and runs longer finishes after a faster producer
that started later. Two producers coexist in the web process: the AI worker
thread (`_snapshot_self_heal` / `_refresh_ai_tools_for_cycle`) and the internal
`/system/ai-tabs/report?refresh=true` audit, both of which call
`generate_market_snapshot`.

`_load_from_disk_if_needed` already refuses to adopt an older generation from
disk; publishing had no equivalent guard, so the slow producer's older snapshot
replaced the newer one.
"""

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from app.cache.snapshot_cache import SnapshotCache

GEN_OLD = 1_000_000.0
GEN_NEW = 2_000_000.0


def _rows(price):
    return [{"ticker": "PETR4", "symbol": "PETR4", "price": price, "master_score": 50.0}]


def _payload(price, generated_at, source):
    return {"signals": _rows(price), "source": source, "stale": False, "generated_at": generated_at}


class MissionC18GenerationOrderingTests(unittest.TestCase):
    def _cache(self, tmp):
        return SnapshotCache()

    def test_older_generation_does_not_overwrite_a_newer_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"SNAPSHOT_CACHE_FILE": str(Path(tmp) / "snapshot.json")}):
                cache = self._cache(tmp)
                cache.update(_payload(42.0, GEN_NEW, "engine_B"))
                cache.update(_payload(10.0, GEN_OLD, "engine_A"))

                final = cache.get()
                self.assertEqual(final["generated_at"], GEN_NEW)
                self.assertEqual(final["signals"][0]["price"], 42.0)
                self.assertEqual(final["source"], "engine_B")

    def test_slow_producer_finishing_last_does_not_win(self):
        """C18.4 scenario 1+2, ordered with Events rather than sleeps."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"SNAPSHOT_CACHE_FILE": str(Path(tmp) / "snapshot.json")}):
                cache = self._cache(tmp)
                b_published = threading.Event()

                def slow_producer_a():
                    # Built first (GEN_OLD) but published last.
                    b_published.wait(10)
                    cache.update(_payload(10.0, GEN_OLD, "engine_A"))

                def fast_producer_b():
                    cache.update(_payload(42.0, GEN_NEW, "engine_B"))
                    b_published.set()

                threads = [
                    threading.Thread(target=slow_producer_a, name="A"),
                    threading.Thread(target=fast_producer_b, name="B"),
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(15)

                self.assertFalse(any(thread.is_alive() for thread in threads))
                self.assertEqual(cache.get()["signals"][0]["price"], 42.0)

    def test_newer_generation_replaces_the_current_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"SNAPSHOT_CACHE_FILE": str(Path(tmp) / "snapshot.json")}):
                cache = self._cache(tmp)
                cache.update(_payload(10.0, GEN_OLD, "engine_A"))
                cache.update(_payload(42.0, GEN_NEW, "engine_B"))

                self.assertEqual(cache.get()["signals"][0]["price"], 42.0)

    def test_same_generation_republish_is_accepted(self):
        """The ai_tools enrichment republishes the base generation unchanged."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"SNAPSHOT_CACHE_FILE": str(Path(tmp) / "snapshot.json")}):
                cache = self._cache(tmp)
                cache.update(_payload(42.0, GEN_NEW, "engine_B"))

                enriched = dict(cache.get())
                enriched["ai_tools"] = {"flow": [{"ticker": "PETR4"}]}
                cache.update(enriched)

                final = cache.get()
                self.assertTrue(final.get("ai_tools"))
                self.assertEqual(final["signals"][0]["price"], 42.0)

    def test_publish_without_a_generation_still_lands(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"SNAPSHOT_CACHE_FILE": str(Path(tmp) / "snapshot.json")}):
                cache = self._cache(tmp)
                cache.update(_payload(10.0, GEN_OLD, "engine_A"))
                cache.update({"signals": _rows(42.0), "source": "engine_B", "stale": False})

                self.assertEqual(cache.get()["signals"][0]["price"], 42.0)

    def test_clear_resets_the_generation_floor(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"SNAPSHOT_CACHE_FILE": str(Path(tmp) / "snapshot.json")}):
                cache = self._cache(tmp)
                cache.update(_payload(42.0, GEN_NEW, "engine_B"))
                cache.clear()
                cache.update(_payload(10.0, GEN_OLD, "engine_A"))

                self.assertEqual(cache.get()["signals"][0]["price"], 10.0)


if __name__ == "__main__":
    unittest.main()
