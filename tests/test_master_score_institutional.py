import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.ai.ai_master_score import apply_master_scores_by_ticker, run_master_score
from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED, AUDIT_CAUTION
from app.api import routes_public_market_live
from app.engine.market_snapshot_engine import build_snapshot_payload
from app.services import ranking, workspace_service
from app.web import routes_radar as web_radar


def _row(ticker="PETR4", direction="BUY", audit_status=AUDIT_APPROVED, **overrides):
    bearish = direction == "SHORT"
    row = {
        "ticker": ticker,
        "symbol": ticker,
        "score": 92.0,
        "signal": direction,
        "trade_action": direction,
        "decision_ready": True,
        "decision_state": "SHORT_READY" if bearish else "BUY_READY",
        "can_trade": True,
        "data_quality": "cached",
        "price": 37.5,
        "volume": 1_500_000,
        "avg_volume": 900_000,
        "rel_volume": 1.66,
        "vwap": 37.0 if not bearish else 38.0,
        "above_vwap": not bearish,
        "adx": 28.0,
        "atr_pct": 1.6,
        "momentum": -1.4 if bearish else 1.4,
        "change_pct": -1.2 if bearish else 1.2,
        "market_regime_state": "bear_trend" if bearish else "bull_trend",
        "trend_strength": 72.0,
        "audit_status": audit_status,
        "auditor_status": audit_status,
        "audit_score": 92.0 if audit_status == AUDIT_APPROVED else 68.0 if audit_status == AUDIT_CAUTION else 22.0,
        "audit_confidence": "Alta" if audit_status == AUDIT_APPROVED else "Media" if audit_status == AUDIT_CAUTION else "Baixa",
        "audit_blocks": ["baixa liquidez"] if audit_status == AUDIT_BLOCKED else [],
        "audit_warnings": ["conflito leve"] if audit_status == AUDIT_CAUTION else [],
        "audit_summary": f"{ticker}: {audit_status}",
        "auditor_approved": audit_status != AUDIT_BLOCKED,
        "blocked_by_auditor": audit_status == AUDIT_BLOCKED,
        "auditor": {
            "audit_status": audit_status,
            "audit_score": 92.0 if audit_status == AUDIT_APPROVED else 68.0 if audit_status == AUDIT_CAUTION else 22.0,
            "audit_blocks": ["baixa liquidez"] if audit_status == AUDIT_BLOCKED else [],
            "audit_warnings": ["conflito leve"] if audit_status == AUDIT_CAUTION else [],
            "blocked_by_auditor": audit_status == AUDIT_BLOCKED,
            "auditor_approved": audit_status != AUDIT_BLOCKED,
        },
    }
    row.update(overrides)
    return row


def _tool(ticker, tool, score, state, comment=""):
    return {
        "ticker": ticker,
        "tool": tool,
        "score": score,
        "state": state,
        "ai_comment": comment,
        "metrics": {
            f"{tool}_score": score,
            f"{tool}_state": state,
            "risk_score": score if tool == "risk" else None,
            "regime_state": state if tool == "regime" else None,
        },
    }


def _bullish_tools(ticker="PETR4", risk_state="low_risk", risk_score=22):
    return {
        "flow": [_tool(ticker, "flow", 88, "institutional_buying", "fluxo comprador bull")],
        "liquidity": [_tool(ticker, "liquidity", 78, "liquidity_zone", "liquidez adequada")],
        "trend": [_tool(ticker, "trend", 86, "uptrend_structure", "tendencia de alta")],
        "momentum": [_tool(ticker, "momentum", 80, "momentum_expansion", "momentum comprador bull")],
        "smart_money": [_tool(ticker, "smart_money", 87, "institutional_accumulation", "smart money acumulando")],
        "risk": [_tool(ticker, "risk", risk_score, risk_state, risk_state)],
        "news": [_tool(ticker, "news", 62, "news_available", "noticia positiva bull")],
        "macro": [_tool(ticker, "macro", 58, "macro_context_available", "macro positivo bull")],
        "regime": [_tool(ticker, "regime", 84, "bull_trend", "regime bull_trend")],
    }


def _bearish_tools(ticker="PETR4"):
    return {
        "flow": [_tool(ticker, "flow", 88, "institutional_distribution", "fluxo vendedor bear")],
        "liquidity": [_tool(ticker, "liquidity", 78, "liquidity_zone", "liquidez no lado vendedor")],
        "trend": [_tool(ticker, "trend", 86, "downtrend_structure", "tendencia de baixa")],
        "momentum": [_tool(ticker, "momentum", 80, "bearish_momentum", "momentum vendedor bear")],
        "smart_money": [_tool(ticker, "smart_money", 87, "institutional_distribution", "smart money distribuindo")],
        "risk": [_tool(ticker, "risk", 24, "low_risk", "risco baixo")],
        "news": [_tool(ticker, "news", 62, "news_available", "noticia negativa bear")],
        "macro": [_tool(ticker, "macro", 58, "macro_context_available", "macro bear")],
        "regime": [_tool(ticker, "regime", 84, "bear_trend", "regime bear_trend")],
    }


class InstitutionalMasterScoreTests(unittest.TestCase):
    def test_bullish_strong_contract_explains_context(self):
        master = run_master_score([_row()], ai_tools=_bullish_tools(), market_pulse={"sentiment": "bullish"})[0]

        self.assertEqual(master["master_direction"], "BULLISH")
        self.assertEqual(master["master_status"], AUDIT_APPROVED)
        self.assertGreaterEqual(master["master_score"], 80)
        self.assertEqual(master["master_conviction"], "Alta")
        self.assertIn(master["master_confidence"], {"Alta", "Média"})
        self.assertIn(master["master_risk"], {"Baixo", "Moderado"})
        for field in (
            "flow_reason",
            "liquidity_reason",
            "trend_reason",
            "momentum_reason",
            "smart_money_reason",
            "risk_reason",
            "news_reason",
            "macro_reason",
            "regime_reason",
        ):
            self.assertIn(field, master["master_reasoning"])
        self.assertTrue(master["opinion_change_conditions"])

    def test_bearish_strong_contract(self):
        master = run_master_score([_row(direction="SHORT")], ai_tools=_bearish_tools(), market_pulse={"sentiment": "bearish"})[0]

        self.assertEqual(master["master_direction"], "BEARISH")
        self.assertGreaterEqual(master["master_score"], 80)
        self.assertEqual(master["master_conviction"], "Alta")

    def test_score_high_without_context_stays_neutral(self):
        tools = _bullish_tools()
        tools["flow"] = [_tool("PETR4", "flow", 95, "institutional_buying", "fluxo comprador bull")]
        for key in ("liquidity", "trend", "momentum", "smart_money", "news", "macro", "regime"):
            tools[key] = [_tool("PETR4", key, 50, "neutral", "neutro")]

        master = run_master_score([_row(score=99.0)], ai_tools=tools)[0]

        self.assertEqual(master["master_direction"], "NEUTRAL")
        self.assertLessEqual(master["master_score"], 59)
        self.assertEqual(master["master_conviction"], "Baixa")

    def test_auditor_blocked_overrides_high_score(self):
        master = run_master_score(
            [_row(audit_status=AUDIT_BLOCKED, score=99.0)],
            ai_tools=_bullish_tools(),
            market_pulse={"sentiment": "bullish"},
        )[0]

        self.assertEqual(master["master_status"], AUDIT_BLOCKED)
        self.assertEqual(master["master_direction"], "NEUTRAL")
        self.assertLessEqual(master["master_score"], 39)
        self.assertFalse(master["decision_ready"])
        self.assertIn("NÃO OPERAR AGORA", master["master_summary"])

    def test_auditor_caution_caps_score(self):
        master = run_master_score([_row(audit_status=AUDIT_CAUTION)], ai_tools=_bullish_tools())[0]

        self.assertEqual(master["master_status"], AUDIT_CAUTION)
        self.assertLessEqual(master["master_score"], 79)
        self.assertEqual(master["master_visual_status"], "Atenção")

    def test_low_consensus_from_conflicting_ias_lowers_conviction(self):
        tools = _bullish_tools()
        tools["liquidity"] = [_tool("PETR4", "liquidity", 82, "liquidity_zone", "bear liquidity sell")]
        tools["smart_money"] = [_tool("PETR4", "smart_money", 86, "institutional_distribution", "bear distribution")]
        tools["macro"] = [_tool("PETR4", "macro", 74, "macro_context_available", "bear macro")]
        tools["regime"] = [_tool("PETR4", "regime", 84, "bear_trend", "bear regime")]

        master = run_master_score([_row()], ai_tools=tools)[0]

        self.assertEqual(master["master_conviction"], "Baixa")
        self.assertLessEqual(master["master_score"], 59)
        self.assertGreaterEqual(master["master_consensus"]["bullish_count"], 4)
        self.assertGreaterEqual(master["master_consensus"]["bearish_count"], 4)

    def test_high_risk_is_reflected_in_master_risk(self):
        master = run_master_score(
            [_row()],
            ai_tools=_bullish_tools(risk_state="high_risk", risk_score=88),
        )[0]

        self.assertEqual(master["master_risk"], "Alto")
        self.assertLess(master["master_score"], 80)

    def test_provider_suffix_matches_canonical_flow_row(self):
        row = _row("PETR4")
        row["ticker"] = "PETR4.SA"
        master = run_master_score(
            [row],
            ai_tools={"flow": [_tool("PETR4", "flow", 88, "institutional_buying", "fluxo comprador bull")]},
        )[0]

        self.assertEqual(master["ticker"], "PETR4")
        self.assertEqual(master["master_components"]["flow"], 88)
        self.assertIn("institutional_buying", master["master_reasoning"]["flow_reason"])

    def test_zero_flow_score_is_a_valid_symbol_scoped_reading(self):
        rows = [_row("PETR4"), _row("AAPL")]
        rows[0]["ticker"] = "PETR4.SA"
        tools = {
            "flow": [
                _tool("PETR4", "flow", 0, "distribution_risk", "distribuição confirmada"),
                _tool("AAPL", "flow", 72, "institutional_interest", "buyer interest"),
            ]
        }

        by_ticker = {row["ticker"]: row for row in run_master_score(rows, ai_tools=tools)}
        petr4, aapl = by_ticker["PETR4"], by_ticker["AAPL"]

        self.assertEqual(petr4["master_components"]["flow"], 0)
        self.assertIn("distribution_risk", petr4["master_reasoning"]["flow_reason"])
        self.assertEqual(aapl["master_components"]["flow"], 72)
        self.assertNotIn("distribution_risk", aapl["master_reasoning"]["flow_reason"])

    def test_apply_master_score_blocks_unconfirmed_actionable_signal(self):
        neutral = run_master_score([_row()], ai_tools={"news": [_tool("PETR4", "news", 95, "news_available", "positive bull")]})[0]
        applied = apply_master_scores_by_ticker([_row()], [neutral])[0]

        self.assertEqual(applied["master_direction"], "NEUTRAL")
        self.assertFalse(applied["decision_ready"])
        self.assertIn("master_score_context_not_confirmed", applied["blocked_reasons"])

    def test_snapshot_propagates_master_score(self):
        payload = build_snapshot_payload([_row()], source="test")
        signal = payload["signals"][0]

        self.assertIn("master_scores", payload)
        self.assertIn("master_score", signal)
        self.assertIn(signal["master_direction"], {"BULLISH", "BEARISH", "NEUTRAL"})
        self.assertIn("master_reasoning", signal)

    def test_workspace_consumes_master_score(self):
        signal = {
            **_row(),
            "master_score": 84.0,
            "master_score_raw": 84.0,
            "master_score_source_scale": "0_100",
            "master_direction": "BULLISH",
            "master_status": "APPROVED",
        }
        bootstrap = {"brand": "StockNewsBR", "pricing": {"trial_days": 30}, "launch_roadmap": {}, "ai_modules": [], "social_features": {}}
        metrics = {"engine_cycles": 1, "signals_generated": 1, "assets_scanned": 1, "cache_age": 0, "http_requests": 0, "ws_connections": 0, "chat_messages": 0}
        with patch.object(workspace_service, "get_public_bootstrap", return_value=bootstrap), patch.object(
            workspace_service, "get_metrics_snapshot", return_value=metrics
        ), patch.object(workspace_service, "get_snapshot", return_value={"signals": [signal], "ai_tools": workspace_service._empty_ai_outputs(), "master_score": signal, "master_scores": [signal]}), patch.object(
            workspace_service, "get_ranking", return_value=[]
        ), patch.object(workspace_service, "get_posts", return_value=[]), patch.object(
            workspace_service, "get_help_center_blueprint", return_value={"guides": []}
        ), patch.object(workspace_service, "get_media_status", return_value={}), patch.object(
            workspace_service, "get_push_status", return_value={}
        ), patch.object(workspace_service, "get_user_workspace_layout", return_value={"tabs": ["home"], "pinned_ticker": "PETR4", "opened_popouts": []}), patch.object(
            workspace_service, "get_layout", return_value={"tabs": [{"id": "home", "title": "Home"}]}
        ), patch.object(workspace_service, "list_room_messages", return_value=[]), patch.object(
            workspace_service, "persist_ai_alert_history", side_effect=lambda value: value
        ):
            payload = workspace_service.get_workspace_data(user_id=7, channel="web")

        self.assertEqual(payload["top_signals"][0]["master_score"], 8.4)
        self.assertEqual(payload["top_signals"][0]["master_score_raw"], 84.0)
        self.assertEqual(payload["top_signals"][0]["master_score_source_scale"], "0_100")
        self.assertEqual(payload["market_snapshot"]["master_score"]["master_score"], 8.4)
        self.assertEqual(payload["market_snapshot"]["master_score"]["master_score_raw"], 84.0)
        self.assertEqual(payload["market_snapshot"]["master_score"]["master_score_source_scale"], "0_100")
        self.assertEqual(payload["market_snapshot"]["master_score"]["master_direction"], "BULLISH")

    def test_ranking_and_radar_consume_master_score(self):
        low_source_high_master = {
            **_row("PETR4"),
            "score": 20.0,
            "score_source_scale": "0_100",
            "master_score": 82.0,
            "master_score_raw": 82.0,
            "master_score_source_scale": "0_100",
            "ranking_opportunity_score": 82.0,
            "ranking_opportunity_source_scale": "0_100",
            "ranking_eligible": True,
            "master_direction": "BULLISH",
            "master_status": "APPROVED",
            "events": ["momentum"],
        }
        high_source_low_master = {
            **_row("VALE3"),
            "score": 95.0,
            "score_source_scale": "0_100",
            "master_score": 61.0,
            "master_score_raw": 61.0,
            "master_score_source_scale": "0_100",
            "ranking_opportunity_score": 61.0,
            "ranking_opportunity_source_scale": "0_100",
            "ranking_eligible": True,
            "master_direction": "BULLISH",
            "master_status": "APPROVED",
            "events": ["momentum"],
        }

        with patch.object(ranking, "get_snapshot_info", return_value={"signals": 2, "age_seconds": 0, "timestamp": 1, "has_signals": True, "is_empty": False}), patch.object(
            ranking, "get_snapshot_signals", return_value=[low_source_high_master, high_source_low_master]
        ):
            ranked = ranking.get_ranking(force_refresh=True)

        with patch.object(web_radar, "get_snapshot_signals", return_value=[high_source_low_master, low_source_high_master]):
            radar = web_radar.get_radar()

        self.assertEqual(ranked[0]["score"], 8.2)
        self.assertEqual(ranked[0]["master_score"], 8.2)
        self.assertEqual(ranked[0]["master_score_raw"], 82.0)
        self.assertEqual(ranked[0]["master_score_source_scale"], "0_100")
        self.assertEqual(radar[0]["ticker"], "PETR4")
        self.assertEqual(radar[0]["score"], 8.2)
        self.assertEqual(radar[0]["master_score"], 8.2)
        self.assertEqual(radar[0]["master_score_raw"], 82.0)
        self.assertEqual(radar[0]["master_score_source_scale"], "0_100")

    def test_public_insight_exposes_master_score(self):
        row = {
            **_row(),
            "master_score": 83.0,
            "master_score_raw": 83.0,
            "master_score_source_scale": "0_100",
            "master_direction": "BULLISH",
            "master_status": "APPROVED",
            "master_summary": "Fluxo comprador e regime favorável.",
        }
        with patch.object(routes_public_market_live, "get_snapshot_ticker", return_value=row), patch.object(
            routes_public_market_live, "_load_chart_data_fast", return_value=[]
        ):
            payload = routes_public_market_live.public_market_insight("PETR4")

        self.assertEqual(payload["master_score"], 8.3)
        self.assertEqual(payload["master_score_raw"], 83.0)
        self.assertEqual(payload["master_score_source_scale"], "0_100")
        self.assertEqual(payload["master_direction"], "BULLISH")


if __name__ == "__main__":
    unittest.main()
