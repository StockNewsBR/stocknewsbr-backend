import unittest

from app.ai.ai_market_pulse import market_pulse


class MarketPulseActionableTests(unittest.TestCase):
    def test_ignores_blocked_score_only_rows(self):
        rows = [
            {
                "symbol": "AAA",
                "score": 91,
                "score_source_scale": "0_100",
                "master_score_raw": 91,
                "master_score_source_scale": "0_100",
                "ranking_opportunity_source_scale": "0_100",
                "signal": "BUY",
                "trade_action": "BUY",
                "price": 0,
                "volume": 0,
                "data_quality": "score_only",
                "decision_ready": False,
                "blocked_reasons": ["price_missing_or_zero"],
            },
            {
                "symbol": "BBB",
                "score": 65,
                "score_source_scale": "0_100",
                "master_score_raw": 65,
                "master_score_source_scale": "0_100",
                "ranking_opportunity_source_scale": "0_100",
                "signal": "BUY",
                "trade_action": "BUY",
                "price": 10,
                "volume": 1000,
                "data_quality": "priced",
                "decision_ready": True,
            },
            {
                "symbol": "CCC",
                "score": 35,
                "score_source_scale": "0_100",
                "master_score_raw": 35,
                "master_score_source_scale": "0_100",
                "ranking_opportunity_source_scale": "0_100",
                "signal": "SHORT",
                "trade_action": "SHORT",
                "price": 10,
                "volume": 1000,
                "data_quality": "priced",
                "decision_ready": True,
            },
        ]

        pulse = market_pulse(rows)

        self.assertEqual(pulse["total_signals"], 2)
        self.assertEqual(pulse["bullish_signals"], 1)
        self.assertEqual(pulse["bearish_signals"], 1)
        self.assertEqual(pulse["bullish_candidates"], 2)
        self.assertEqual(pulse["actionable_bullish"], 1)
        self.assertEqual(pulse["bearish_candidates"], 1)
        self.assertEqual(pulse["actionable_bearish"], 1)
        self.assertEqual(pulse["blocked_signals"], 1)
        self.assertEqual(pulse["signal_groups"]["blocked_signals"][0]["ticker"], "AAA")
        self.assertEqual(pulse["sentiment"], "neutral")

    def test_score_without_actionable_decision_is_neutral(self):
        pulse = market_pulse(
            [
                {
                    "symbol": "AAA",
                    "score": 95,
                    "score_source_scale": "0_100",
                    "master_score_raw": 95,
                    "master_score_source_scale": "0_100",
                    "ranking_opportunity_source_scale": "0_100",
                    "price": 10,
                    "volume": 1000,
                    "data_quality": "priced",
                    "decision_ready": True,
                }
            ]
        )

        self.assertEqual(pulse["total_signals"], 0)
        self.assertEqual(pulse["bullish_signals"], 0)
        self.assertEqual(pulse["bearish_signals"], 0)
        self.assertEqual(pulse["bullish_candidates"], 1)
        self.assertEqual(pulse["blocked_signals"], 0)
        self.assertEqual(pulse["sentiment"], "neutral")

    def test_wait_watch_rows_are_watchlist_not_active_trade(self):
        pulse = market_pulse(
            [
                {
                    "symbol": "AAA",
                    "score": 82,
                    "score_source_scale": "0_100",
                    "master_score_raw": 82,
                    "master_score_source_scale": "0_100",
                    "ranking_opportunity_source_scale": "0_100",
                    "signal": "WATCH_BUY",
                    "trade_action": "WATCH_BUY",
                    "price": 10,
                    "volume": 1000,
                    "data_quality": "priced",
                    "decision_ready": False,
                    "decision_state": "WATCH",
                },
                {
                    "symbol": "BBB",
                    "score": 28,
                    "score_source_scale": "0_100",
                    "master_score_raw": 28,
                    "master_score_source_scale": "0_100",
                    "ranking_opportunity_source_scale": "0_100",
                    "signal": "WAIT",
                    "price": 10,
                    "volume": 1000,
                    "data_quality": "priced",
                    "decision_ready": False,
                    "decision_state": "WAIT",
                },
            ]
        )

        self.assertEqual(pulse["total_signals"], 0)
        self.assertEqual(pulse["bullish_signals"], 0)
        self.assertEqual(pulse["bearish_signals"], 0)
        self.assertEqual(pulse["bullish_candidates"], 1)
        self.assertEqual(pulse["bearish_candidates"], 1)
        self.assertEqual(pulse["watchlist_candidates"], 2)
        self.assertEqual(pulse["blocked_signals"], 0)
        self.assertEqual(pulse["sentiment"], "neutral")

    def test_provider_failed_rows_do_not_count_as_actionable(self):
        pulse = market_pulse(
            [
                {
                    "symbol": "AAA",
                    "score": 95,
                    "score_source_scale": "0_100",
                    "master_score_raw": 95,
                    "master_score_source_scale": "0_100",
                    "ranking_opportunity_source_scale": "0_100",
                    "signal": "BUY",
                    "trade_action": "BUY",
                    "price": 10,
                    "volume": 1000,
                    "data_quality": "priced",
                    "provider_status": "provider_failed",
                    "decision_ready": True,
                }
            ]
        )

        self.assertEqual(pulse["total_signals"], 0)
        self.assertEqual(pulse["bullish_signals"], 0)
        self.assertEqual(pulse["bearish_signals"], 0)
        self.assertEqual(pulse["sentiment"], "neutral")

    def test_stale_rows_do_not_count_as_actionable(self):
        pulse = market_pulse(
            [
                {
                    "symbol": "AAA",
                    "score": 80,
                    "score_source_scale": "0_100",
                    "master_score_raw": 80,
                    "master_score_source_scale": "0_100",
                    "ranking_opportunity_source_scale": "0_100",
                    "signal": "SHORT",
                    "trade_action": "SHORT",
                    "price": 10,
                    "volume": 1000,
                    "data_quality": "priced",
                    "stale": True,
                    "decision_ready": True,
                }
            ]
        )

        self.assertEqual(pulse["total_signals"], 0)
        self.assertEqual(pulse["bullish_signals"], 0)
        self.assertEqual(pulse["bearish_signals"], 0)
        self.assertEqual(pulse["sentiment"], "neutral")

    def test_normalized_display_scores_keep_orientation_counts(self):
        pulse = market_pulse(
            [
                {
                    "symbol": "DSPB",
                    "score": 8.7,
                    "score_source_scale": "0_10",
                    "master_score": 8.7,
                    "master_score_source_scale": "0_10",
                    "ranking_opportunity_score": 8.7,
                    "ranking_opportunity_source_scale": "0_10",
                    "signal": "BUY",
                    "trade_action": "BUY",
                    "price": 10,
                    "volume": 1000,
                    "data_quality": "priced",
                    "decision_ready": True,
                },
                {
                    "symbol": "DSPS",
                    "score": 2.8,
                    "score_source_scale": "0_10",
                    "master_score": 2.8,
                    "master_score_source_scale": "0_10",
                    "ranking_opportunity_score": 2.8,
                    "ranking_opportunity_source_scale": "0_10",
                    "signal": "SHORT",
                    "trade_action": "SHORT",
                    "price": 10,
                    "volume": 1000,
                    "data_quality": "priced",
                    "decision_ready": True,
                },
            ]
        )

        self.assertEqual(pulse["bullish_candidates"], 1)
        self.assertEqual(pulse["bearish_candidates"], 1)
        self.assertEqual(pulse["actionable_bullish"], 1)
        self.assertEqual(pulse["actionable_bearish"], 1)
        self.assertEqual(pulse["total_signals"], 2)

    def test_mixed_raw_and_display_scores_keep_candidate_counts(self):
        pulse = market_pulse(
            [
                {
                    "symbol": "RAWB",
                    "score": 87,
                    "score_source_scale": "0_100",
                    "master_score_raw": 87,
                    "master_score_source_scale": "0_100",
                    "ranking_opportunity_score": 87,
                    "ranking_opportunity_source_scale": "0_100",
                    "signal": "BUY",
                    "trade_action": "BUY",
                    "price": 10,
                    "volume": 1000,
                    "data_quality": "priced",
                    "decision_ready": True,
                },
                {
                    "symbol": "DSPS",
                    "score": 2.8,
                    "score_source_scale": "0_10",
                    "master_score": 2.8,
                    "master_score_source_scale": "0_10",
                    "ranking_opportunity_score": 2.8,
                    "ranking_opportunity_source_scale": "0_10",
                    "signal": "SHORT",
                    "trade_action": "SHORT",
                    "price": 10,
                    "volume": 1000,
                    "data_quality": "priced",
                    "decision_ready": True,
                },
            ]
        )

        self.assertEqual(pulse["bullish_candidates"], 1)
        self.assertEqual(pulse["bearish_candidates"], 1)
        self.assertEqual(pulse["actionable_bullish"], 1)
        self.assertEqual(pulse["actionable_bearish"], 1)
        self.assertEqual(pulse["total_signals"], 2)


if __name__ == "__main__":
    unittest.main()
