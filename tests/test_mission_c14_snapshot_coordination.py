"""Mission C14 - snapshot write coordination between concurrent producers.

The AI worker is the only snapshot writer that performs a read-modify-write: it
reads a snapshot, attaches `ai_tools`, and republishes it. Every other producer
(`generate_market_snapshot`) publishes freshly built full state, where
last-writer-wins is correct.

That makes the AI worker the one path that can revert a snapshot published
between its read and its write -- in-process (its worker thread races the
internal `/system/ai-tabs/report?refresh=true` audit, which also generates a
snapshot) and across processes (local runs where `uvicorn main:app` and
`python worker.py` share one `runtime/` directory).
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.cache.snapshot_cache import SnapshotCache
from app.services.ai_alert_history_service import AI_TOOL_KEYS
from app.system import ai_worker


def _rows(price, score):
    return [{"ticker": "PETR4", "symbol": "PETR4", "price": price, "master_score": score}]


def _tools():
    return {key: [{"ticker": "PETR4", "signal": "BUY", "state": "active"}] for key in AI_TOOL_KEYS}


class MissionC14SnapshotCoordinationTests(unittest.TestCase):
    def _cache(self, tmp):
        return SnapshotCache()

    def _run_enrichment(self, cache, held_snapshot):
        with patch.object(ai_worker, "update_snapshot", cache.update), patch.object(
            ai_worker, "get_snapshot", cache.get
        ), patch.object(
            ai_worker, "build_ai_tool_payload", return_value=_tools()
        ), patch.object(
            ai_worker, "persist_ai_alert_history", side_effect=lambda tools: tools
        ):
            return ai_worker._refresh_ai_tools_for_cycle([], held_snapshot)

    def test_ai_tools_enrichment_does_not_revert_a_fresher_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"SNAPSHOT_CACHE_FILE": str(Path(tmp) / "snapshot.json")}):
                cache = self._cache(tmp)
                cache.update({"source": "seed", "stale": False, "signals": _rows(10.0, 10)})

                # What the AI worker cycle is holding when it starts enriching.
                held = cache.get()

                # A concurrent producer publishes fresher prices in the meantime.
                cache.update({"source": "engine", "stale": False, "signals": _rows(42.0, 90)})

                self._run_enrichment(cache, held)

                final = cache.get()
                self.assertTrue(final.get("ai_tools"), "ai_tools must still be attached")
                self.assertEqual(
                    final["signals"][0]["price"],
                    42.0,
                    "the fresher snapshot must not be reverted by ai_tools enrichment",
                )

    def test_ai_tools_enrichment_attaches_tools_without_a_race(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"SNAPSHOT_CACHE_FILE": str(Path(tmp) / "snapshot.json")}):
                cache = self._cache(tmp)
                cache.update({"source": "seed", "stale": False, "signals": _rows(10.0, 10)})

                held = cache.get()
                result = self._run_enrichment(cache, held)

                final = cache.get()
                self.assertTrue(result["history_persisted"])
                self.assertTrue(final.get("ai_tools"))
                self.assertEqual(final["signals"][0]["price"], 10.0)


if __name__ == "__main__":
    unittest.main()
