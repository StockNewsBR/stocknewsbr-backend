import unittest

from app.ai.ai_master_score import confidence_label
from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED
from app.ai.strategic_panel import (
    ACTION_CONFIRMED,
    ACTION_NO_TRADE,
    ACTION_WAIT,
    OPERATIONAL_LEVEL_KEYS,
    STATE_BUY,
    STATE_SELL,
    STATE_WAIT,
    TRADE_NO_TRADE,
    build_strategic_panel,
    validate_canonical_analysis,
)
from app.services.score_display import attach_master_score_display_contract

_LEVEL_FIELDS = ("entrada_referencia", "alvo", "invalidacao", "liquidez_alvo")
_GEOMETRY_FIELDS = _LEVEL_FIELDS + ("potencial_pct", "risco_pct", "reward_risk")
_STATE_BIAS = {STATE_BUY: "BULLISH", STATE_SELL: "BEARISH", STATE_WAIT: "NEUTRAL"}


def _panel_texts(panel):
    """Every free-text surface the panel ships to the user."""
    texts = [
        panel["strategic_panel_summary"],
        panel["recommended_action_detail"] or "",
        panel["auditor_block"]["summary"] or "",
    ]
    texts.extend(str(item.get("reason") or "") for item in panel["why"])
    texts.extend(str(item) for item in panel["opinion_change_conditions"])
    return texts


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
                    # A blocked ticker resolves to NEUTRO_AGUARDAR: bias follows the state,
                    # never the stale bullish thesis.
                    "bias": "NEUTRAL",
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
                self._assert_single_resolved_state(panel)

    def _assert_single_resolved_state(self, panel):
        """T4: decisão, viés, direção and the top card all read from one state."""
        state = panel["resolved_state"]
        self.assertIn(state, _STATE_BIAS)
        bias = _STATE_BIAS[state]
        self.assertEqual(panel["canonical_analysis"]["bias"], bias)
        self.assertEqual(panel["bias"], bias)
        self.assertEqual(panel["probable_direction_block"]["direction"], bias)
        self.assertEqual(panel["probable_direction_block"]["resolved_state"], state)
        if state == STATE_WAIT:
            self.assertNotIn(panel["canonical_analysis"]["suggested_trade"], {"BUY", "SELL", "SHORT", "COVER"})
            # No active buy/sell thesis may survive next to a neutral bias.
            for text in _panel_texts(panel):
                self.assertNotRegex(
                    text.lower(),
                    r"tese (vendedora|compradora) ativa",
                    f"active thesis copy beside {state}",
                )

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
        for field in _GEOMETRY_FIELDS:
            self.assertIsNone(panel[field], field)


class Mission68NullLevelTests(unittest.TestCase):
    """T1: an unknown level is null and is never spoken about."""

    def _blind_row(self, ticker="BA", **overrides):
        return _row(
            ticker,
            price=None,
            resistance=0.0,
            support=0.0,
            target=0.0,
            invalidation_price=0.0,
            master_direction="NEUTRAL",
            decision_status="NO_TRADE",
            decision_ready=False,
            trade_action="NO_DECISION",
            signal="NO_DECISION",
            market_regime_state="range",
            **overrides,
        )

    def test_zero_levels_are_emitted_as_null(self):
        panel = build_strategic_panel(self._blind_row())
        for field in _GEOMETRY_FIELDS:
            self.assertIsNone(panel[field], field)
            self.assertNotEqual(panel[field], 0.0, field)

    def test_null_levels_emit_no_invalidation_or_level_copy(self):
        panel = build_strategic_panel(
            self._blind_row(
                master_reasoning={
                    "trend_reason": "Invalidacao: acima de 0,00.",
                    "liquidity_reason": "Alvo em R$0,00 sem confirmacao.",
                    "flow_reason": "Fluxo institucional comprador confirmado.",
                },
                opinion_change_conditions=["perda da VWAP", "stop em 0,00"],
            )
        )
        self.assertIsNone(panel["invalidacao"])
        self.assertIsNone(panel["recommended_action_detail"])
        for text in _panel_texts(panel):
            lowered = text.lower()
            self.assertNotIn("invalidac", lowered.replace("ç", "c"), text)
            self.assertNotIn("0,00", text)
            self.assertNotIn("0.00", text)
        # The clause that carried no level survives untouched.
        self.assertTrue(any("fluxo" in text.lower() for text in _panel_texts(panel)))

    def test_no_side_never_mirrors_support_into_alvo(self):
        # NO_TRADE has no side, so support/resistance carry no target/invalidation meaning.
        panel = build_strategic_panel(
            _row(
                "COST",
                price=100.0,
                support=95.0,
                resistance=105.0,
                master_direction="NEUTRAL",
                decision_status="NO_TRADE",
                decision_ready=False,
                trade_action="NO_DECISION",
                signal="NO_DECISION",
                market_regime_state="range",
            )
        )
        self.assertEqual(panel["entrada_referencia"], 100.0)
        self.assertIsNone(panel["alvo"])
        self.assertIsNone(panel["invalidacao"])


class Mission68RsiNullSafetyTests(unittest.TestCase):
    """T2: a missing RSI decides nothing and says nothing."""

    def _reasoning(self):
        return {
            "momentum_reason": "RSI 0.0 em sobrevenda extrema.",
            "trend_reason": "Tendencia de alta confirmada pelo volume.",
        }

    def test_absent_rsi_is_null_and_drops_oversold_copy(self):
        panel = build_strategic_panel(_row("BA", master_reasoning=self._reasoning()))
        self.assertIsNone(panel["rsi"])
        for text in _panel_texts(panel):
            lowered = _deaccent_lower(text)
            self.assertNotIn("sobrevenda", lowered, text)
            self.assertNotIn("sobrecompra", lowered, text)
            self.assertNotRegex(lowered, r"\brsi\b", text)

    def test_zero_rsi_is_treated_as_missing(self):
        panel = build_strategic_panel(_row("BA", rsi=0.0, master_reasoning=self._reasoning()))
        self.assertIsNone(panel["rsi"])
        for text in _panel_texts(panel):
            self.assertNotIn("sobrevenda", _deaccent_lower(text), text)

    def test_missing_rsi_does_not_change_the_decision(self):
        without_rsi = build_strategic_panel(_row("BA", price=100.0, target=105.0, invalidation_price=98.0))
        with_zero_rsi = build_strategic_panel(
            _row("BA", price=100.0, target=105.0, invalidation_price=98.0, rsi=0.0)
        )
        for field in ("resolved_state", "bias", "recommended_action", "confidence_pct", "reward_risk"):
            self.assertEqual(without_rsi[field], with_zero_rsi[field], field)

    def test_real_rsi_survives(self):
        panel = build_strategic_panel(_row("BA", rsi=28.4, master_reasoning=self._reasoning()))
        self.assertEqual(panel["rsi"], 28.4)
        self.assertTrue(
            any("sobrevenda" in _deaccent_lower(text) for text in _panel_texts(panel)),
            "real RSI must keep its reasoning",
        )


class Mission68ResolvedStateTests(unittest.TestCase):
    """T4: bias always equals the resolved state, on every path."""

    def test_bias_equals_resolved_state_across_paths(self):
        cases = {
            STATE_BUY: _row("BBAS3", price=100.0, target=105.0, invalidation_price=98.0),
            STATE_SELL: _row(
                "VALE3",
                price=100.0,
                master_direction="BEARISH",
                trade_action="SHORT",
                signal="SHORT",
                trade_direction="short",
                decision_state="SHORT_READY",
                market_regime_state="bear_trend",
                target=95.0,
                invalidation_price=101.0,
            ),
            # Touching resistance: geometry fails closed into NEUTRO_AGUARDAR.
            STATE_WAIT: _row("PETR4", price=40.94, resistance=40.96, support=40.79),
        }
        for expected_state, row in cases.items():
            with self.subTest(state=expected_state):
                panel = build_strategic_panel(row)
                self.assertEqual(panel["resolved_state"], expected_state)
                bias = _STATE_BIAS[expected_state]
                self.assertEqual(panel["bias"], bias)
                self.assertEqual(panel["canonical_analysis"]["bias"], bias)
                self.assertEqual(panel["probable_direction_block"]["direction"], bias)

    def test_wait_state_never_shows_a_directional_label(self):
        panel = build_strategic_panel(_row("PETR4", price=40.94, resistance=40.96, support=40.79))
        self.assertEqual(panel["resolved_state"], STATE_WAIT)
        self.assertLessEqual(panel["confidence_pct"], 60.0)
        self.assertEqual(panel["recommended_action"], ACTION_WAIT)
        self.assertIn("Neutra", panel["probable_direction_block"]["label"])

    def test_wait_state_drops_stale_active_thesis_copy(self):
        # The exact BA regression: "Tese vendedora ativa" printed beside BIAS Neutro.
        panel = build_strategic_panel(
            _row(
                "BA",
                price=214.25,
                master_direction="BEARISH",
                decision_status="NO_TRADE",
                decision_ready=False,
                trade_action="NO_DECISION",
                signal="NO_DECISION",
                market_regime_state="range",
                audit_summary="Tese vendedora ativa. Invalidacao: acima de 0,00.",
            )
        )
        self.assertEqual(panel["resolved_state"], STATE_WAIT)
        self.assertEqual(panel["bias"], "NEUTRAL")
        for text in _panel_texts(panel):
            lowered = _deaccent_lower(text)
            self.assertNotIn("tese vendedora ativa", lowered, text)
            self.assertNotIn("0,00", text)

    def test_directional_state_keeps_its_thesis_and_real_levels(self):
        panel = build_strategic_panel(
            _row(
                "BBAS3",
                price=100.0,
                target=105.0,
                invalidation_price=98.0,
                audit_summary="Tese compradora ativa. Alvo em R$105.00.",
            )
        )
        self.assertEqual(panel["resolved_state"], STATE_BUY)
        self.assertIn("Tese compradora ativa", panel["auditor_block"]["summary"])
        self.assertIn("105.00", panel["auditor_block"]["summary"])

    def test_high_risk_wait_resolves_neutral(self):
        panel = build_strategic_panel(
            _row("CVX", price=100.0, target=105.0, invalidation_price=98.0, master_risk="Alto")
        )
        self.assertEqual(panel["recommended_action"], ACTION_WAIT)
        self.assertEqual(panel["resolved_state"], STATE_WAIT)
        self.assertEqual(panel["bias"], "NEUTRAL")


class Mission68SingleScoreSourceTests(unittest.TestCase):
    """T1: one score, one number, one declared scale."""

    def test_master_score_block_declares_its_0_100_origin(self):
        # The regression: master_score 8.0 (0..100) was published as "8.0 / 10"
        # because the display contract guessed the scale from the magnitude.
        panel = build_strategic_panel(_row("PETR4", master_score=8.0))
        block = panel["master_score_block"]
        self.assertEqual(block["score"], 8.0)
        self.assertEqual(block["score_raw"], 8.0)
        self.assertEqual(block["score_source_scale"], "0_100")
        self.assertEqual(block["score_0_10"], 0.8)

    def test_display_contract_renders_one_score_on_one_scale(self):
        for raw, expected in ((8.0, 0.8), (80.0, 8.0), (100.0, 10.0)):
            with self.subTest(raw=raw):
                panel = build_strategic_panel(_row("PETR4", master_score=raw))
                displayed = attach_master_score_display_contract(
                    {"tool": "master_score", "master_score_block": panel["master_score_block"]}
                )["master_score_block"]
                # The block's own 0..10 value and the display contract agree: one number.
                self.assertEqual(displayed["score"], expected)
                self.assertEqual(panel["master_score_block"]["score_0_10"], expected)

    def test_score_and_confidence_are_not_the_same_metric(self):
        # "CONFIANÇA 8%" was the 0..10 score reprinted as a percent.
        panel = build_strategic_panel(_row("PETR4", master_score=86.0, master_confidence_pct=41.0))
        self.assertEqual(panel["confidence_pct"], 41.0)
        self.assertNotEqual(panel["confidence_pct"], panel["master_score_block"]["score_0_10"])


class Mission68ConfidenceLabelTests(unittest.TestCase):
    """T2: the word always derives from the number. Bands <35 / 35-65 / >65."""

    def test_eight_percent_never_reads_alta(self):
        panel = build_strategic_panel(
            _row(
                "PETR4",
                master_confidence="Alta",  # stale inherited word: must be ignored
                master_confidence_pct=8.0,
                master_direction="NEUTRAL",
                decision_status="NO_TRADE",
                decision_ready=False,
                trade_action="NO_DECISION",
                signal="NO_DECISION",
                market_regime_state="range",
            )
        )
        self.assertEqual(panel["resolved_state"], STATE_WAIT)
        self.assertEqual(panel["confidence_pct"], 8.0)
        self.assertEqual(panel["confidence_label"], "Baixa")
        self.assertEqual(panel["master_score_block"]["confidence"], "Baixa")
        self.assertNotIn("Alta", panel["master_score_block"]["confidence_visual"])

    def test_label_follows_the_bands(self):
        for pct, expected in ((0.0, "Baixa"), (34.9, "Baixa"), (35.0, "Média"), (65.0, "Média"), (65.1, "Alta"), (100.0, "Alta")):
            with self.subTest(pct=pct):
                self.assertEqual(confidence_label(pct), expected)

    def test_panel_label_always_matches_panel_number(self):
        rows = (
            _row("BBAS3", price=100.0, target=105.0, invalidation_price=98.0, master_confidence_pct=90.0),
            _row("PETR4", price=40.94, resistance=40.96, support=40.79, master_confidence_pct=90.0),
            _row("CVX", price=100.0, target=105.0, invalidation_price=98.0, master_risk="Alto"),
            _row("BBDC4", master_status=AUDIT_BLOCKED, audit_status=AUDIT_BLOCKED, master_confidence_pct=95.0),
        )
        for row in rows:
            with self.subTest(ticker=row["ticker"]):
                panel = build_strategic_panel(row)
                self.assertEqual(panel["confidence_label"], confidence_label(panel["confidence_pct"]))
                self.assertEqual(panel["master_score_block"]["confidence"], panel["confidence_label"])

    def test_geometry_cap_demotes_the_word_with_the_number(self):
        # Touching resistance caps confidence at 60 => the word must fall out of "Alta".
        panel = build_strategic_panel(
            _row("PETR4", price=40.94, resistance=40.96, support=40.79, master_confidence_pct=95.0)
        )
        self.assertLessEqual(panel["confidence_pct"], 60.0)
        self.assertNotEqual(panel["confidence_label"], "Alta")


class Mission68OperationalLevelsTests(unittest.TestCase):
    """T3: NÍVEIS OPERACIONAIS carries prices, never loose phrases."""

    def test_every_key_is_present_and_numeric_or_null(self):
        panel = build_strategic_panel(
            _row("BBAS3", price=100.0, target=105.0, invalidation_price=98.0, support=97.0, resistance=106.0)
        )
        levels = panel["operational_levels"]
        self.assertEqual(tuple(levels), OPERATIONAL_LEVEL_KEYS)
        for key, level in levels.items():
            price = level["price"]
            self.assertTrue(price is None or isinstance(price, float), key)
            self.assertNotEqual(price, 0.0, key)
            self.assertTrue(level["label"], key)
        self.assertEqual(levels["entrada_referencia"]["price"], 100.0)
        self.assertEqual(levels["alvo"]["price"], 105.0)
        self.assertEqual(levels["invalidacao"]["price"], 98.0)
        self.assertEqual(levels["suporte"]["price"], 97.0)
        self.assertEqual(levels["resistencia"]["price"], 106.0)

    def test_unknown_level_emits_null_price_and_null_reason(self):
        # A level with no price must say NOTHING: a bare phrase is the unreadable bullet.
        panel = build_strategic_panel(
            _row(
                "BBDC4",
                price=None,
                support=0.0,
                resistance=0.0,
                target=0.0,
                invalidation_price=0.0,
                master_direction="NEUTRAL",
                decision_status="NO_TRADE",
                decision_ready=False,
                trade_action="NO_DECISION",
                signal="NO_DECISION",
                market_regime_state="range",
            )
        )
        for key, level in panel["operational_levels"].items():
            self.assertIsNone(level["price"], key)
            self.assertIsNone(level["reason"], key)

    def test_invalidation_phrase_becomes_the_reason_of_a_priced_level(self):
        panel = build_strategic_panel(
            _row(
                "BBAS3",
                price=100.0,
                target=105.0,
                invalidation_price=98.0,
                opinion_change_conditions=["perda da VWAP", "fluxo vendedor persistente"],
            )
        )
        invalidation = panel["operational_levels"]["invalidacao"]
        self.assertEqual(invalidation["price"], 98.0)
        self.assertIn("VWAP", invalidation["reason"])
        # Every level that carries a reason carries a price to hang it on.
        for key, level in panel["operational_levels"].items():
            if level["reason"]:
                self.assertIsNotNone(level["price"], key)

    def test_levels_never_emit_a_zero_price(self):
        panel = build_strategic_panel(
            _row("VALE3", price=190.0, support=0.0, resistance=0.0, target=0.0, invalidation_price=0.0)
        )
        for key, level in panel["operational_levels"].items():
            self.assertNotEqual(level["price"], 0.0, key)


class Mission68TopCardCoherenceTests(unittest.TestCase):
    """T4: the top card reads the resolved state, not the stale raw direction."""

    def test_master_score_block_direction_equals_resolved_state(self):
        rows = (
            _row("BBAS3", price=100.0, target=105.0, invalidation_price=98.0),
            _row("PETR4", price=40.94, resistance=40.96, support=40.79),
            _row("BBDC4", master_status=AUDIT_BLOCKED, audit_status=AUDIT_BLOCKED, decision_status="BLOCKED"),
            _row("CVX", price=100.0, target=105.0, invalidation_price=98.0, master_risk="Alto"),
        )
        for row in rows:
            with self.subTest(ticker=row["ticker"]):
                panel = build_strategic_panel(row)
                block = panel["master_score_block"]
                self.assertEqual(block["resolved_state"], panel["resolved_state"])
                self.assertEqual(block["direction"], panel["bias"])
                self.assertEqual(block["direction"], _STATE_BIAS[panel["resolved_state"]])
                self.assertEqual(block["direction_label"], panel["probable_direction_block"]["visual_label"].split(" ", 1)[1])

    def test_blocked_bullish_row_never_shows_a_buy_top_card(self):
        # The BA regression: raw direction BULLISH survived onto the top card
        # while the panel below had already resolved to NEUTRO_AGUARDAR.
        panel = build_strategic_panel(
            _row("BBDC4", master_status=AUDIT_BLOCKED, audit_status=AUDIT_BLOCKED, decision_status="BLOCKED")
        )
        self.assertEqual(panel["resolved_state"], STATE_WAIT)
        self.assertEqual(panel["master_score_block"]["direction"], "NEUTRAL")
        self.assertNotIn("Compradora", panel["master_score_block"]["direction_visual"])


def _deaccent_lower(value):
    import unicodedata

    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).lower()


if __name__ == "__main__":
    unittest.main()
