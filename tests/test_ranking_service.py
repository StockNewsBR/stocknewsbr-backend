import unittest
from unittest.mock import patch

try:
    from app.services import ranking
    from app.system.system_metrics import provider_call_context
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
        ranking._RANK_CACHE["snapshot_signature"] = ""
        ranking.ALLOW_NETWORK_FALLBACK = False

    def tearDown(self):
        ranking._RANK_CACHE["data"] = list(self.original_cache.get("data", []))
        ranking._RANK_CACHE["timestamp"] = float(self.original_cache.get("timestamp", 0.0))
        ranking._RANK_CACHE["snapshot_signature"] = str(self.original_cache.get("snapshot_signature", ""))
        ranking.ALLOW_NETWORK_FALLBACK = self.original_network_fallback

    def _actionable_row(self, ticker, score=88, **overrides):
        row = {
            "ticker": ticker,
            "score": score,
            "trend": 0.12,
            "breakout": True,
            "price": 37.5,
            "volume": 1_000_000,
            "trade_action": "BUY",
            "data_quality": "priced",
            "decision_ready": True,
            "decision_state": "BUY_READY",
        }
        row.update(overrides)
        return row

    def test_uses_snapshot_before_market_download(self):
        snapshot_rows = [
            self._actionable_row("PETR4", score=88)
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

    def test_snapshot_ranking_excludes_blocked_and_score_only_rows(self):
        snapshot_rows = [
            self._actionable_row("PETR4", score=88),
            self._actionable_row(
                "BLOQ1",
                score=99,
                price=0,
                volume=0,
                data_quality="score_only",
                decision_ready=False,
                blocked_reasons=["price_missing_or_zero"],
            ),
            self._actionable_row("STALE1", score=97, stale=True),
            self._actionable_row("NOACTION", score=96, trade_action="WATCH_BUY"),
            self._actionable_row("NOTREADY", score=95, decision_state="NO_TRADE"),
        ]

        with patch.object(
            ranking,
            "get_snapshot_info",
            return_value={"signals": 4, "age_seconds": 5},
        ), patch.object(
            ranking,
            "get_snapshot_signals",
            return_value=snapshot_rows,
        ), patch.object(ranking, "fetch_market_data") as fetch_market_data:
            results = ranking.generate_ranking(force_refresh=True)

        fetch_market_data.assert_not_called()
        self.assertEqual([row["symbol"] for row in results], ["PETR4"])

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

    def test_refreshes_cached_ranking_when_snapshot_signature_changes(self):
        first_rows = [self._actionable_row("PETR4", score=88)]
        second_rows = [self._actionable_row("VALE3", score=91, trend=0.22, price=68.2)]

        with patch.object(
            ranking,
            "get_snapshot_info",
            side_effect=[
                {"signals": 1, "age_seconds": 5, "timestamp": 1000.0, "has_signals": True, "is_empty": False},
                {"signals": 1, "age_seconds": 5, "timestamp": 2000.0, "has_signals": True, "is_empty": False},
            ],
        ), patch.object(
            ranking,
            "get_snapshot_signals",
            side_effect=[first_rows, second_rows],
        ), patch.object(ranking, "fetch_market_data") as fetch_market_data:
            first = ranking.generate_ranking(force_refresh=True)
            second = ranking.generate_ranking(force_refresh=False)

        fetch_market_data.assert_not_called()
        self.assertEqual(first[0]["symbol"], "PETR4")
        self.assertEqual(second[0]["symbol"], "VALE3")

    def test_reuses_cached_ranking_when_only_snapshot_age_changes(self):
        snapshot_rows = [self._actionable_row("PETR4", score=88)]

        with patch.object(
            ranking,
            "get_snapshot_info",
            side_effect=[
                {"signals": 1, "age_seconds": 5, "timestamp": 1000.0, "has_signals": True, "is_empty": False},
                {"signals": 1, "age_seconds": 6, "timestamp": 1000.0, "has_signals": True, "is_empty": False},
            ],
        ), patch.object(
            ranking,
            "get_snapshot_signals",
            return_value=snapshot_rows,
        ) as get_snapshot_signals, patch.object(ranking, "fetch_market_data") as fetch_market_data:
            first = ranking.generate_ranking(force_refresh=True)
            second = ranking.generate_ranking(force_refresh=False)

        fetch_market_data.assert_not_called()
        self.assertEqual(get_snapshot_signals.call_count, 1)
        self.assertEqual(first, second)

    def test_empty_snapshot_does_not_return_stale_cached_ranking(self):
        ranking._RANK_CACHE["data"] = [{"symbol": "PETR4", "score": 88.0}]
        ranking._RANK_CACHE["timestamp"] = 100.0
        ranking._RANK_CACHE["snapshot_signature"] = "old"

        with patch.object(
            ranking,
            "get_snapshot_info",
            return_value={"signals": 0, "age_seconds": None, "timestamp": 3000.0, "has_signals": False, "is_empty": True},
        ), patch.object(
            ranking,
            "get_snapshot_signals",
            return_value=[],
        ), patch.object(ranking, "fetch_market_data") as fetch_market_data:
            results = ranking.generate_ranking(force_refresh=True)

        fetch_market_data.assert_not_called()
        self.assertEqual(results, [])
        self.assertEqual(ranking._RANK_CACHE["data"], [])

    def test_http_context_blocks_network_fallback_even_when_enabled(self):
        ranking.ALLOW_NETWORK_FALLBACK = True

        with patch.object(
            ranking,
            "get_snapshot_info",
            return_value={"signals": 0, "age_seconds": None, "timestamp": 3000.0, "has_signals": False, "is_empty": True},
        ), patch.object(
            ranking,
            "get_snapshot_signals",
            return_value=[],
        ), patch.object(ranking, "fetch_market_data") as fetch_market_data, provider_call_context("http"):
            results = ranking.generate_ranking(force_refresh=True)

        fetch_market_data.assert_not_called()
        self.assertEqual(results, [])

    def test_snapshot_only_ranking_does_not_fetch_even_when_fallback_is_enabled(self):
        ranking.ALLOW_NETWORK_FALLBACK = True

        with patch.object(
            ranking,
            "get_snapshot_info",
            return_value={"signals": 0, "age_seconds": None, "timestamp": 3000.0, "has_signals": False, "is_empty": True},
        ), patch.object(
            ranking,
            "get_snapshot_signals",
            return_value=[],
        ), patch.object(ranking, "fetch_market_data") as fetch_market_data:
            results = ranking.get_ranking(force_refresh=True)

        fetch_market_data.assert_not_called()
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
