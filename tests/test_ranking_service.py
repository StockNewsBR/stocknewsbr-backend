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
            "score_source_scale": "0_100",
            "master_score": score,
            "master_score_raw": score,
            "master_score_source_scale": "0_100",
            "ranking_opportunity_score": score,
            "ranking_opportunity_source_scale": "0_100",
            "ranking_eligible": True,
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
        if row.get("master_score_source_scale") == "0_10" and "master_score_raw" not in overrides:
            row.pop("master_score_raw", None)
            if "score_source_scale" not in overrides:
                row["score_source_scale"] = "0_10"
            if "ranking_opportunity_source_scale" not in overrides:
                row["ranking_opportunity_source_scale"] = "0_10"
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
        self.assertEqual(results[0]["score"], 8.8)
        self.assertEqual(results[0]["master_score"], 8.8)
        self.assertEqual(results[0]["master_score_raw"], 88.0)
        self.assertEqual(results[0]["master_score_source_scale"], "0_100")
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

    def test_snapshot_ranking_dedupes_mixed_scale_scores_on_canonical_display(self):
        normalized_row = self._actionable_row(
            "PETR4",
            score=8.7,
            canonical_symbol="PETR4",
            master_score=8.7,
            master_score_source_scale="0_10",
            ranking_opportunity_score=8.7,
            ranking_opportunity_source_scale="0_10",
            ranking_reason="normalized-row",
        )
        raw_duplicate = self._actionable_row(
            "PETR4.SA",
            score=87.0,
            canonical_symbol="PETR4",
            master_score_raw=87.0,
            master_score=87.0,
            ranking_opportunity_score=87.0,
            ranking_reason="raw-scale-duplicate",
        )
        lower_row = self._actionable_row(
            "VALE3",
            score=86.0,
            canonical_symbol="VALE3",
            master_score_raw=86.0,
            master_score=86.0,
            ranking_opportunity_score=86.0,
            ranking_reason="lower-raw-row",
        )

        def pass_through(rows):
            return rows
        for snapshot_rows in (
            [normalized_row, raw_duplicate, lower_row],
            [raw_duplicate, normalized_row, lower_row],
        ):
            with self.subTest(order=[row["ticker"] for row in snapshot_rows]):
                with patch.object(
                    ranking,
                    "get_snapshot_info",
                    return_value={"signals": 3, "age_seconds": 5},
                ), patch.object(
                    ranking,
                    "get_snapshot_signals",
                    return_value=snapshot_rows,
                ), patch.object(
                    ranking, "ensure_institutional_ranking_rows", side_effect=pass_through
                ), patch.object(
                    ranking, "ensure_historical_confidence_rows", side_effect=pass_through
                ), patch.object(
                    ranking, "ensure_operational_rules_rows", side_effect=pass_through
                ), patch.object(
                    ranking, "ensure_institutional_conviction_rows", side_effect=pass_through
                ), patch.object(
                    ranking, "ensure_institutional_priority_rows", side_effect=pass_through
                ), patch.object(
                    ranking, "ensure_final_decision_rows", side_effect=pass_through
                ), patch.object(
                    ranking, "institutional_ranking_items", side_effect=lambda rows, limit=200: rows
                ), patch.object(ranking, "fetch_market_data") as fetch_market_data:
                    results = ranking.generate_ranking(force_refresh=True)

                fetch_market_data.assert_not_called()
                self.assertEqual([row["symbol"] for row in results], ["PETR4", "VALE3"])
                self.assertEqual(results[0]["score"], 8.7)
                self.assertEqual(results[0]["ranking_opportunity_score"], 8.7)
                self.assertEqual(results[0]["ranking_reason"], "normalized-row")
                self.assertIsNone(results[0].get("master_score_raw"))
                self.assertEqual(results[0]["master_score_source_scale"], "0_10")
                self.assertEqual(results[1]["score"], 8.6)
                self.assertEqual(results[1]["master_score"], 8.6)
                self.assertEqual(results[1]["master_score_raw"], 86.0)
                self.assertEqual(results[1]["master_score_source_scale"], "0_100")

        self.assertEqual(ranking._ranking_sort_score({"ranking_opportunity_score": 87.0}), 8.7)
        self.assertEqual(
            ranking._ranking_sort_score({"ranking_opportunity_score": 87.0, "ranking_opportunity_source_scale": "0_10"}),
            0.0,
        )
        self.assertEqual(ranking._ranking_sort_score({"ranking_opportunity_score": 8.7}), 8.7)
        self.assertEqual(
            ranking._ranking_sort_score({"ranking_opportunity_score": 8.7, "ranking_opportunity_source_scale": "0_100"}),
            0.9,
        )
        self.assertEqual(
            ranking._ranking_sort_score({"ranking_opportunity_score": 8.7, "ranking_opportunity_source_scale": "0_10"}),
            8.7,
        )
        self.assertLess(
            ranking._ranking_order_key({"symbol": "ABCD4", "ranking_opportunity_score": 8.7, "ranking_opportunity_source_scale": "0_10"}),
            ranking._ranking_order_key({"symbol": "ZZZZ4", "ranking_opportunity_score": 8.7, "ranking_opportunity_source_scale": "0_10"}),
        )

    def test_snapshot_ranking_skips_rows_with_only_invalid_score_candidates(self):
        snapshot_rows = [
            self._actionable_row(
                "BAD1",
                score=150.0,
                master_score=150.0,
                master_score_raw=150.0,
                ranking_opportunity_score=150.0,
            )
        ]

        def pass_through(rows):
            return rows
        with patch.object(
            ranking,
            "get_snapshot_info",
            return_value={"signals": 1, "age_seconds": 5},
        ), patch.object(
            ranking,
            "get_snapshot_signals",
            return_value=snapshot_rows,
        ), patch.object(
            ranking, "ensure_institutional_ranking_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_historical_confidence_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_operational_rules_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_institutional_conviction_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_institutional_priority_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_final_decision_rows", side_effect=pass_through
        ), patch.object(
            ranking, "institutional_ranking_items", side_effect=lambda rows, limit=200: rows
        ), patch.object(ranking, "fetch_market_data") as fetch_market_data:
            results = ranking.generate_ranking(force_refresh=True)

        fetch_market_data.assert_not_called()
        self.assertEqual(results, [])

    def test_snapshot_ranking_rejects_explicit_invalid_ranking_score(self):
        snapshot_rows = [
            self._actionable_row(
                "BAD1",
                score=87.0,
                master_score_raw=87.0,
                master_score=87.0,
                ranking_opportunity_score=150.0,
            )
        ]

        def pass_through(rows):
            return rows
        with patch.object(
            ranking,
            "get_snapshot_info",
            return_value={"signals": 1, "age_seconds": 5},
        ), patch.object(
            ranking,
            "get_snapshot_signals",
            return_value=snapshot_rows,
        ), patch.object(
            ranking, "ensure_institutional_ranking_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_historical_confidence_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_operational_rules_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_institutional_conviction_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_institutional_priority_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_final_decision_rows", side_effect=pass_through
        ), patch.object(
            ranking, "institutional_ranking_items", side_effect=lambda rows, limit=200: rows
        ), patch.object(ranking, "fetch_market_data") as fetch_market_data:
            results = ranking.generate_ranking(force_refresh=True)

        fetch_market_data.assert_not_called()
        self.assertEqual(results, [])

    def test_snapshot_ranking_rejects_invalid_canonical_raw_before_fallback(self):
        snapshot_rows = [
            self._actionable_row(
                "BADRAW",
                score=8.7,
                master_score_raw=150.0,
                master_score=8.7,
                ranking_opportunity_score=None,
            )
        ]

        def pass_through(rows):
            return rows
        with patch.object(
            ranking,
            "get_snapshot_info",
            return_value={"signals": 1, "age_seconds": 5},
        ), patch.object(
            ranking,
            "get_snapshot_signals",
            return_value=snapshot_rows,
        ), patch.object(
            ranking, "ensure_institutional_ranking_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_historical_confidence_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_operational_rules_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_institutional_conviction_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_institutional_priority_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_final_decision_rows", side_effect=pass_through
        ), patch.object(
            ranking, "institutional_ranking_items", side_effect=lambda rows, limit=200: rows
        ), patch.object(ranking, "fetch_market_data") as fetch_market_data:
            results = ranking.generate_ranking(force_refresh=True)

        fetch_market_data.assert_not_called()
        self.assertEqual(results, [])

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

    def test_ranking_rsi_is_the_canonical_wilder_rsi(self):
        """ranking must not grow a second RSI implementation again.

        It carried a private Cutler copy (rolling mean) that drifted up to
        ~15 RSI points from the engine on the same candles. Pin ranking's
        published rsi to compute_rsi for a fixed series so any re-divergence
        fails here instead of silently re-splitting the score bands.
        """
        import pandas as pd

        from app.engine.indicators.vector_indicator_engine import compute_rsi

        closes = [
            44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
            45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00,
            46.03, 46.41, 46.22, 45.64, 46.21, 46.25, 45.71, 46.45,
            45.78, 45.35, 44.03, 44.18, 44.22, 44.57,
        ]
        frame = pd.DataFrame({"Close": closes, "Volume": [100] * len(closes)})

        result = ranking.calculate_score("TST", frame)
        expected = compute_rsi(pd.Series(closes, dtype="float64"))

        self.assertIsNotNone(result)
        self.assertEqual(result["rsi"], round(float(expected.iloc[-1]), 2))
        # Pins the direction of the drift: the deleted Cutler copy read 40.9 here.
        self.assertNotAlmostEqual(result["rsi"], 40.90, places=1)

    def test_flat_series_yields_no_score_instead_of_scoring_as_oversold(self):
        """A frozen window has no RSI. It must not publish 0 (= oversold, +25)."""
        import pandas as pd

        frame = pd.DataFrame({"Close": [10.0] * 30, "Volume": [100] * 30})

        self.assertIsNone(ranking.calculate_score("FLAT", frame))



if __name__ == "__main__":
    unittest.main()
