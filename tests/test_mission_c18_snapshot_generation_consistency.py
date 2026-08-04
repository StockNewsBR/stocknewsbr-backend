"""Mission C18 - ai_tools must describe the snapshot generation they ship in.

C14 stopped the AI worker from reverting a fresher snapshot by merging its
ai_tools onto the live payload instead of the copy it held. That fixed the lost
update but left the tools themselves derived from the older generation, so a
published snapshot could carry generation B's `signals` next to generation A's
`ai_tools` -- different prices and scores presented as one snapshot.

Generation identity here is `generated_at`, which is what
`SnapshotCache._normalize_payload` resolves `source_snapshot_id` from.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.cache.snapshot_cache import SnapshotCache
from app.services.ai_alert_history_service import AI_TOOL_KEYS
from app.system import ai_worker

GEN_A = 1_000_000.0
GEN_B = 2_000_000.0


def _rows(price, score):
    return [
        {
            "ticker": "PETR4",
            "symbol": "PETR4",
            "price": price,
            "score": score,
            "master_score": score,
            "signal": "BUY",
            "trade_action": "BUY",
            "master_direction": "BULLISH",
            "volume": 5_000_000,
        }
    ]


def _tool_prices(snapshot):
    return {
        row.get("price")
        for rows in (snapshot.get("ai_tools") or {}).values()
        for row in rows
        if isinstance(row, dict) and "price" in row
    }


class MissionC18SnapshotGenerationTests(unittest.TestCase):
    def _enrich(self, cache, held):
        with patch.object(ai_worker, "update_snapshot", cache.update), patch.object(
            ai_worker, "get_snapshot", cache.get
        ), patch.object(
            ai_worker, "persist_ai_alert_history", side_effect=lambda tools: tools
        ):
            return ai_worker._refresh_ai_tools_for_cycle([], held)

    def test_ai_tools_match_the_generation_they_are_published_with(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"SNAPSHOT_CACHE_FILE": str(Path(tmp) / "snapshot.json")}):
                cache = SnapshotCache()
                cache.update(
                    {"signals": _rows(10.0, 88.0), "source": "seed", "stale": False, "generated_at": GEN_A}
                )
                held = cache.get()

                # A concurrent producer publishes a new generation.
                cache.update(
                    {"signals": _rows(42.0, 55.0), "source": "engine", "stale": False, "generated_at": GEN_B}
                )

                self._enrich(cache, held)

                final = cache.get()
                self.assertEqual(final["generated_at"], GEN_B)
                self.assertEqual(final["signals"][0]["price"], 42.0, "C14: fresher snapshot preserved")

                prices = _tool_prices(final)
                self.assertTrue(prices, "ai_tools must be present")
                self.assertEqual(
                    prices,
                    {42.0},
                    "ai_tools must describe the published generation, not the one the cycle held",
                )

    def test_same_generation_base_keeps_the_engine_supplied_tools(self):
        """A newer *publish* of the same generation must not trigger a rebuild.

        `generate_market_snapshot` returns a payload with no `updated_at`, so the
        live snapshot always looks newer to the merge guard. Rebuilding there
        would discard the engine's audited/master-scored tools and replace them
        with a plain re-derivation.
        """
        engine_tools = {
            key: [{"ticker": "PETR4", "price": 42.0, "signal": "BUY", "state": "active", "engine_enriched": True}]
            for key in AI_TOOL_KEYS
        }

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"SNAPSHOT_CACHE_FILE": str(Path(tmp) / "snapshot.json")}):
                cache = SnapshotCache()
                cache.update(
                    {
                        "signals": _rows(42.0, 55.0),
                        "source": "engine",
                        "stale": False,
                        "generated_at": GEN_B,
                        "ai_tools": engine_tools,
                    }
                )

                # Shape of what generate_market_snapshot hands back: same generation,
                # carrying its own tools, with no updated_at of its own.
                self._enrich(cache, {"generated_at": GEN_B, "ai_tools": engine_tools})

                rows = [row for rows in cache.get()["ai_tools"].values() for row in rows]
                self.assertTrue(rows)
                self.assertTrue(
                    all(row.get("engine_enriched") for row in rows),
                    "engine-supplied tools must survive a same-generation republish",
                )

    def test_ai_tools_match_the_snapshot_without_a_race(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"SNAPSHOT_CACHE_FILE": str(Path(tmp) / "snapshot.json")}):
                cache = SnapshotCache()
                cache.update(
                    {"signals": _rows(10.0, 88.0), "source": "seed", "stale": False, "generated_at": GEN_A}
                )
                held = cache.get()

                result = self._enrich(cache, held)

                final = cache.get()
                self.assertTrue(result["history_persisted"])
                self.assertEqual(final["generated_at"], GEN_A)
                self.assertEqual(final["signals"][0]["price"], 10.0)
                self.assertEqual(_tool_prices(final), {10.0})


if __name__ == "__main__":
    unittest.main()
