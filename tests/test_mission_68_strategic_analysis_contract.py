import unittest

from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED
from app.ai.strategic_panel import (
    ACTION_CONFIRMED,
    ACTION_NO_TRADE,
    ACTION_WAIT,
    TRADE_NO_TRADE,
    build_strategic_panel,
    validate_canonical_analysis,
)


def _row(ticker: str, **overrides):
    row = {
        "ticker": ticker,
        "symbol": ticker,
        "master_score": 86.0,
        "master_direction": "BULLISH",
        "master_status": AUDIT_APPROVED,
        "audit_status": AUDIT_APPROVED,
        "master_conviction": "Alta",
        "master_confidence": "Alta",
        "master_risk": "Baixo",
        "price": 190.0,
        "volume": 1_500_000,
        "data_quality": "cached",
        "decision_status": "READY",
        "decision_ready": True,
        "decision_state": "BUY_READY",
        "trade_action": "BUY",
        "signal": "BUY",
        "trade_direction": "long",
        "market_regime_state": "bull_trend",
    }
    row.update(overrides)
    return row


class Mission68StrategicAnalysisContractTests(unittest.TestCase):
    def test_canonical_analysis_matrix(self):
        cases = (
            {
                "name": "bullish_buy_ready",
                "row": _row("PETR4"),
                "expected": {
                    "direction": "BULLISH",
                    "decision": "READY",
                    "suggested_trade": "BUY",
                    "regime": "BULL_TREND",
                    "bias": "BULLISH",
                    "conclusion": "OPPORTUNITY_CONFIRMED",
                    "validation_status": "NORMALIZED",
                },
            },
            {
                "name": "bearish_short_ready",
                "row": _row(
                    "VALE3",
                    master_direction="BEARISH",
                    trade_action="SHORT",
                    signal="SHORT",
                    trade_direction="short",
                    decision_state="SHORT_READY",
                    market_regime_state="bear_trend",
                ),
                "expected": {
                    "direction": "BEARISH",
                    "decision": "READY",
                    "suggested_trade": "SHORT",
                    "regime": "BEAR_TREND",
                    "bias": "BEARISH",
                    "conclusion": "OPPORTUNITY_CONFIRMED",
                    "validation_status": "NORMALIZED",
                },
            },
            {
                "name": "neutral_wait",
                "row": _row(
                    "ITUB4",
                    master_direction="NEUTRAL",
                    decision_status="NO_TRADE",
                    decision_ready=False,
                    decision_state="NO_TRADE",
                    trade_action="NO_DECISION",
                    signal="NO_DECISION",
                    trade_direction="flat",
                    market_regime_state="range",
                ),
                "expected": {
                    "direction": "NEUTRAL",
                    "decision": "NO_TRADE",
                    "suggested_trade": "NO_TRADE",
                    "regime": "RANGE",
                    "bias": "NEUTRAL",
                    "conclusion": "OBSERVE",
                    "validation_status": "NORMALIZED",
                },
            },
            {
                "name": "auditor_blocked",
                "row": _row(
                    "BBDC4",
                    master_status=AUDIT_BLOCKED,
                    audit_status=AUDIT_BLOCKED,
                    decision_status="BLOCKED",
                    decision_ready=False,
                    decision_state="DO_NOT_TRADE",
                    audit_blocks=["auditor_blocked"],
                ),
                "expected": {
                    "direction": "BULLISH",
                    "decision": "BLOCKED",
                    "suggested_trade": "NO_TRADE",
                    "regime": "BULL_TREND",
                    "bias": "BULLISH",
                    "conclusion": "NO_TRADE",
                    "validation_status": "NORMALIZED",
                },
            },
        )

        for case in cases:
            with self.subTest(case=case["name"]):
                panel = build_strategic_panel(case["row"])
                analysis = panel["canonical_analysis"]
                for field, expected in case["expected"].items():
                    self.assertEqual(analysis[field], expected)

    def test_aapl_contradiction_is_rejected_conservatively(self):
        panel = build_strategic_panel(
            _row(
                "AAPL",
                master_direction="BULLISH",
                trade_action="SHORT",
                signal="SHORT",
                trade_direction="short",
                decision_state="SHORT_READY",
                market_regime_state="bear_trend",
            )
        )

        analysis = panel["canonical_analysis"]
        self.assertEqual(analysis["direction"], "BULLISH")
        self.assertEqual(analysis["decision"], "CONFLICT")
        self.assertEqual(analysis["suggested_trade"], "NO_TRADE")
        self.assertEqual(analysis["conclusion"], "CONFLICT")
        self.assertEqual(analysis["validation_status"], "REJECTED")
        self.assertIn("direction_vs_suggested_trade", analysis["validation_reasons"])
        self.assertEqual(panel["recommended_action"], ACTION_NO_TRADE)
        self.assertTrue(panel["no_trade_now"])

    def test_validator_normalizes_locale_but_never_accepts_input_conclusion(self):
        analysis = validate_canonical_analysis(
            {
                "direction": "Compradora",
                "decision": "pronta",
                "suggested_trade": "compra",
                "regime": "tendencia de alta",
                "bias": "long",
                "conclusion": "NO_TRADE",
            }
        )

        self.assertEqual(analysis["direction"], "BULLISH")
        self.assertEqual(analysis["decision"], "READY")
        self.assertEqual(analysis["suggested_trade"], "BUY")
        self.assertEqual(analysis["regime"], "BULL_TREND")
        self.assertEqual(analysis["bias"], "BULLISH")
        self.assertEqual(analysis["conclusion"], "OPPORTUNITY_CONFIRMED")
        self.assertEqual(analysis["validation_status"], "NORMALIZED")


class Mission68TradeGeometryTests(unittest.TestCase):
    def test_petr4_touching_resistance_waits_and_caps_confidence(self):
        # entry 40.94, resistance/target 40.96 (upside 0.02), invalidation 40.79
        # => R:R 0.13, potential below min => fail-closed WAIT, confidence <= 60.
        panel = build_strategic_panel(_row("PETR4", price=40.94, resistance=40.96, support=40.79))
        self.assertEqual(panel["recommended_action"], ACTION_WAIT)
        self.assertLessEqual(panel["confidence_pct"], 60.0)
        self.assertEqual(panel["canonical_analysis"]["suggested_trade"], TRADE_NO_TRADE)
        self.assertEqual(panel["alvo"], 40.96)
        self.assertEqual(panel["invalidacao"], 40.79)
        self.assertIn("40,96", panel["recommended_action_detail"])
        # Touching resistance must never be reused as the liquidity target.
        self.assertIsNone(panel["liquidez_alvo"])

    def test_target_below_entry_is_no_trade(self):
        panel = build_strategic_panel(_row("VALE3", price=190.0, target=189.0, stop=185.0))
        self.assertEqual(panel["canonical_analysis"]["suggested_trade"], TRADE_NO_TRADE)
        self.assertEqual(panel["recommended_action"], ACTION_WAIT)

    def test_reward_risk_below_threshold_waits(self):
        # entry 100, target 101 (upside 1%), invalidation 99 => R:R 1.0 < 1.5.
        panel = build_strategic_panel(_row("ITUB4", price=100.0, target=101.0, invalidation_price=99.0))
        self.assertEqual(panel["recommended_action"], ACTION_WAIT)
        self.assertEqual(panel["reward_risk"], 1.0)
        self.assertEqual(panel["canonical_analysis"]["suggested_trade"], TRADE_NO_TRADE)

    def test_breakout_with_next_target_stays_buy(self):
        # entry 100, target 105 (upside 5%), invalidation 98 => R:R 2.5 >= 1.5.
        panel = build_strategic_panel(_row("BBAS3", price=100.0, target=105.0, invalidation_price=98.0))
        self.assertEqual(panel["canonical_analysis"]["suggested_trade"], "BUY")
        self.assertEqual(panel["recommended_action"], ACTION_CONFIRMED)
        self.assertEqual(panel["reward_risk"], 2.5)

    def test_flow_without_reading_caps_confidence_below_100(self):
        panel = build_strategic_panel(
            _row(
                "WEGE3",
                price=100.0,
                target=105.0,
                invalidation_price=98.0,
                master_reasoning={
                    "flow_reason": "Sem leitura",
                    "trend_reason": "tendência de alta confirmada",
                },
            )
        )
        self.assertLess(panel["confidence_pct"], 100.0)

    def test_null_levels_stay_null_never_zero(self):
        panel = build_strategic_panel(
            _row(
                "BBDC4",
                price=None,
                master_direction="NEUTRAL",
                decision_status="NO_TRADE",
                decision_ready=False,
                trade_action="NO_DECISION",
                signal="NO_DECISION",
                market_regime_state="range",
            )
        )
        for field in ("entrada_referencia", "alvo", "invalidacao", "potencial_pct", "risco_pct", "reward_risk", "liquidez_alvo"):
            self.assertIsNone(panel[field], field)


if __name__ == "__main__":
    unittest.main()
