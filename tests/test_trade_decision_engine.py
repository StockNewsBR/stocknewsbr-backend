import unittest

from app.ai.trade_decision import evaluate_trade_coherence, resolve_trade_action, summarize_trade_decision


class TradeDecisionEngineTests(unittest.TestCase):
    def test_resolves_bullish_buy(self):
        row = {
            "ticker": "PETR4",
            "institutional_flow_score": 86,
            "institutional_flow_state": "institutional_buying",
            "smart_money_score": 84,
            "smart_money_state": "smart_money_active",
            "accumulation_score": 81,
            "accumulation_state": "accumulation",
            "breakout_probability_score": 79,
            "breakout_probability_state": "ready_to_break",
            "heat_map_score": 76,
            "heat_map_state": "strong_buying",
            "market_regime_state": "bull_trend",
            "above_vwap": True,
            "rel_volume": 1.8,
            "trend_strength": 68,
            "score": 88,
        }

        decision = resolve_trade_action(row)

        self.assertEqual(decision["trade_action"], "BUY")
        self.assertEqual(decision["signal"], "BUY")
        self.assertGreaterEqual(decision["trade_confidence"], 60)

    def test_resolves_bearish_short(self):
        row = {
            "ticker": "VALE3",
            "institutional_flow_score": 18,
            "institutional_flow_state": "distribution_risk",
            "smart_money_score": 22,
            "smart_money_state": "retail_noise",
            "accumulation_score": 14,
            "accumulation_state": "distribution_or_weak",
            "breakout_probability_score": 20,
            "breakout_probability_state": "not_ready",
            "heat_map_score": 30,
            "heat_map_state": "strong_selling",
            "market_regime_state": "bear_trend",
            "chart_regime_state": "trend_down",
            "liquidity_event": "sweep_high_reject",
            "above_vwap": False,
            "change_pct": -2.4,
            "rel_volume": 1.6,
            "trend_strength": 18,
            "score": 22,
        }

        decision = resolve_trade_action(row)

        self.assertEqual(decision["trade_action"], "SHORT")
        self.assertEqual(decision["signal"], "SHORT")
        self.assertGreaterEqual(decision["trade_confidence"], 60)
        self.assertGreater(decision["short_confidence"], decision["long_confidence"])
        self.assertEqual(decision["chart_regime_state"], "trend_down")

    def test_warns_against_early_short_exit_in_bearish_continuation(self):
        row = {
            "ticker": "PETR4",
            "institutional_flow_state": "distribution_risk",
            "market_regime_state": "bear_trend",
            "chart_regime_state": "trend_down",
            "smart_money_state": "retail_noise",
            "above_vwap": False,
            "rel_volume": 1.25,
            "trend_strength": 62,
        }

        decision = evaluate_trade_coherence(row, "COVER", bullish=38, bearish=66)

        self.assertEqual(decision["final_action"], "COVER")
        self.assertIn("exit_short_against_downtrend_continuation", decision["warnings"])
        self.assertIn("cover_against_bearish_flow", decision["warnings"])

    def test_blocks_buy_in_downtrend(self):
        row = {
            "ticker": "PETR4",
            "institutional_flow_score": 86,
            "institutional_flow_state": "institutional_buying",
            "smart_money_score": 82,
            "smart_money_state": "smart_money_active",
            "accumulation_score": 80,
            "breakout_probability_score": 78,
            "breakout_probability_state": "ready_to_break",
            "heat_map_score": 76,
            "market_regime_state": "bear_trend",
            "above_vwap": False,
            "rel_volume": 1.7,
            "trend_strength": 70,
            "score": 86,
        }

        decision = resolve_trade_action(row)

        self.assertNotEqual(decision["trade_action"], "BUY")
        self.assertIn("buy_in_downtrend", decision["blocked_reasons"])
        self.assertEqual(decision["risk_level"], "alto")

    def test_blocks_sell_into_bullish_squeeze(self):
        row = {
            "ticker": "AAPL",
            "institutional_flow_score": 72,
            "institutional_flow_state": "institutional_interest",
            "smart_money_score": 78,
            "smart_money_state": "smart_money_active",
            "accumulation_score": 70,
            "breakout_probability_score": 45,
            "heat_map_score": 68,
            "market_regime_state": "bull_trend",
            "volatility_squeeze_state": "squeeze_ready",
            "above_vwap": True,
            "rel_volume": 1.3,
            "trend_strength": 62,
            "score": 66,
        }

        decision = evaluate_trade_coherence(row, "SELL", bullish=62, bearish=58)

        self.assertNotEqual(decision["final_action"], "SELL")
        self.assertTrue(
            set(decision["blocked_reasons"]).intersection(
                {"sell_into_bullish_squeeze", "sell_against_bull_regime"}
            )
        )

    def test_blocks_breakout_without_volume(self):
        row = {
            "ticker": "MSFT",
            "institutional_flow_score": 82,
            "institutional_flow_state": "institutional_buying",
            "smart_money_score": 80,
            "smart_money_state": "smart_money_active",
            "accumulation_score": 75,
            "breakout_probability_score": 86,
            "breakout_probability_state": "ready_to_break",
            "heat_map_score": 80,
            "market_regime_state": "bull_trend",
            "above_vwap": True,
            "rel_volume": 0.72,
            "volume_score": 10,
            "trend_strength": 68,
            "score": 86,
        }

        decision = resolve_trade_action(row)

        self.assertNotEqual(decision["trade_action"], "BUY")
        self.assertIn("breakout_without_volume", decision["blocked_reasons"])

    def test_missing_provider_volume_raises_risk_and_changes_trigger(self):
        row = {
            "ticker": "AAPL",
            "institutional_flow_score": 68,
            "institutional_flow_state": "institutional_interest",
            "smart_money_score": 66,
            "smart_money_state": "smart_money_interest",
            "market_regime_state": "bull_trend",
            "chart_regime_state": "trend_up",
            "above_vwap": True,
            "rel_volume": 1.0,
            "volume_known": False,
            "trend_strength": 64,
        }

        decision = evaluate_trade_coherence(row, "BUY", bullish=68, bearish=45)

        self.assertEqual(decision["risk_level"], "medio")
        self.assertIn("volume real ausente no provider publico", decision["risk"])
        self.assertIn("provider publico nao trouxe volume confiavel", decision["trigger"])
        self.assertNotIn("breakout_without_volume", decision["blocked_reasons"])

    def test_blocks_short_against_smart_money_and_bull_regime(self):
        row = {
            "ticker": "NVDA",
            "institutional_flow_score": 30,
            "institutional_flow_state": "monitoring",
            "smart_money_score": 82,
            "smart_money_state": "smart_money_active",
            "accumulation_score": 35,
            "breakout_probability_score": 28,
            "heat_map_score": 34,
            "market_regime_state": "bull_trend",
            "above_vwap": True,
            "rel_volume": 1.1,
            "trend_strength": 64,
            "score": 38,
        }

        decision = evaluate_trade_coherence(row, "SHORT", bullish=42, bearish=66)

        self.assertNotEqual(decision["final_action"], "SHORT")
        self.assertIn("short_in_bulltrend", decision["blocked_reasons"])

    def test_summarize_trade_decision_uses_top_row(self):
        rows = [
            {"ticker": "PETR4", "score": 88, "trade_confidence": 72, "trade_action": "BUY"},
            {"ticker": "VALE3", "score": 79, "trade_confidence": 65, "trade_action": "SHORT"},
        ]

        decision = summarize_trade_decision(rows)

        self.assertEqual(decision["ticker"], "PETR4")
        self.assertEqual(decision["trade_action"], "BUY")

    def test_summarize_trade_decision_without_rows_stays_neutral(self):
        decision = summarize_trade_decision([])

        self.assertEqual(decision["trade_action"], "NO_DECISION")
        self.assertEqual(decision["trade_direction"], "flat")
        self.assertFalse(decision["decision_ready"])


if __name__ == "__main__":
    unittest.main()
