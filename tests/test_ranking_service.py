import unittest
from unittest.mock import patch

try:
    from app.services import ranking
    IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    IMPORT_ERROR = exc


@unittest.skipIf(IMPORT_ERROR is not None, f"runtime dependency unavailable: {IMPORT_ERROR}")
class RankingServiceTests(unittest.TestCase):
    def setUp(self):
        self.original_cache = dict(ranking._RANK_CACHE)
        self.original_network_fallback = ranking.ALLOW_NETWORK_FALLBACK
        ranking._RANK_CACHE["data"] = []
        ranking._RANK_CACHE["timestamp"] = 0.0
        ranking.ALLOW_NETWORK_FALLBACK = False

    def tearDown(self):
        ranking._RANK_CACHE["data"] = list(self.original_cache.get("data", []))
        ranking._RANK_CACHE["timestamp"] = float(self.original_cache.get("timestamp", 0.0))
        ranking.ALLOW_NETWORK_FALLBACK = self.original_network_fallback

    def test_uses_snapshot_before_market_download(self):
        snapshot_rows = [
            {
                "ticker": "PETR4",
                "score": 88,
                "trend": 0.12,
                "breakout": True,
                "price": 37.5,
            }
        ]

        with patch.object(
            ranking,
            "get_snapshot_info",
            return_value={"signals": 1, "age_seconds": 5},
        ), patch.object(
            ranking,
            "get_snapshot_signals",
            return_value=snapshot_rows,
        ), patch.object(ranking, "fetch_market_data") as fetch_market_data:
            results = ranking.generate_ranking(force_refresh=True)

        fetch_market_data.assert_not_called()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["symbol"], "PETR4")
        self.assertEqual(results[0]["score"], 88.0)
        self.assertTrue(results[0]["breakout"])

    def test_skips_network_download_when_snapshot_is_empty(self):
        with patch.object(
            ranking,
            "get_snapshot_info",
            return_value={"signals": 0, "age_seconds": None},
        ), patch.object(
            ranking,
            "get_snapshot_signals",
            return_value=[],
        ), patch.object(ranking, "fetch_market_data") as fetch_market_data:
            results = ranking.generate_ranking(force_refresh=True)

        fetch_market_data.assert_not_called()
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
