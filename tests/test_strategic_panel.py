import unittest
from unittest.mock import patch

from app.ai.ai_master_score import run_master_score
from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED, AUDIT_CAUTION
from app.ai.strategic_panel import (
    ACTION_CONFIRMED,
    ACTION_NO_TRADE,
    ACTION_OBSERVE,
    ACTION_WAIT,
    build_strategic_panels,
)
from app.api import routes_public_market_live
from app.engine.market_snapshot_engine import build_snapshot_payload
from app.services import workspace_service


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
        "vwap": 38.0 if bearish else 37.0,
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


def _panel(row=None, tools=None, market_pulse=None):
    source_row = row or _row()
    ai_tools = tools or _bullish_tools(source_row["ticker"])
    master = run_master_score([source_row], ai_tools=ai_tools, market_pulse=market_pulse)[0]
    return build_strategic_panels([master], ai_tools=ai_tools)[0]


class StrategicPanelTests(unittest.TestCase):
    def test_bullish_strong_panel_reads_in_under_10_seconds(self):
        panel = _panel(market_pulse={"sentiment": "bullish"})

        self.assertEqual(panel["master_score_block"]["direction"], "BULLISH")
        self.assertEqual(panel["probable_direction_block"]["label"], "Compradora")
        self.assertEqual(panel["recommended_action"], ACTION_CONFIRMED)
        self.assertEqual(panel["risk_block"]["level"], "Baixo")
        self.assertEqual(panel["risk_block"]["source"], "risk_ia")
        self.assertTrue(panel["why"])
        self.assertNotIn(panel["recommended_action"], {"BUY", "SELL"})
        self.assertLessEqual(len(panel["strategic_panel_summary"]), 220)

    def test_bearish_strong_panel_keeps_direction_without_sell_signal(self):
        panel = _panel(row=_row(direction="SHORT"), tools=_bearish_tools(), market_pulse={"sentiment": "bearish"})

        self.assertEqual(panel["master_score_block"]["direction"], "BEARISH")
        self.assertEqual(panel["probable_direction_block"]["label"], "Vendedora")
        self.assertEqual(panel["recommended_action"], ACTION_CONFIRMED)
        self.assertNotIn(panel["recommended_action"], {"BUY", "SELL", "SHORT"})

    def test_neutral_panel_recommends_observe_or_wait(self):
        tools = {"news": [_tool("PETR4", "news", 95, "news_available", "noticia positiva bull")]}
        panel = _panel(tools=tools)

        self.assertEqual(panel["master_score_block"]["direction"], "NEUTRAL")
        self.assertIn(panel["recommended_action"], {ACTION_OBSERVE, ACTION_WAIT})
        self.assertEqual(panel["probable_direction_block"]["label"], "Neutra")

    def test_auditor_statuses_are_visible(self):
        approved = _panel(row=_row(audit_status=AUDIT_APPROVED))
        caution = _panel(row=_row(audit_status=AUDIT_CAUTION))
        blocked = _panel(row=_row(audit_status=AUDIT_BLOCKED, score=99.0))

        self.assertEqual(approved["auditor_block"]["status"], AUDIT_APPROVED)
        self.assertEqual(caution["auditor_block"]["status"], AUDIT_CAUTION)
        self.assertEqual(blocked["auditor_block"]["status"], AUDIT_BLOCKED)
        self.assertEqual(blocked["recommended_action"], ACTION_NO_TRADE)
        self.assertTrue(blocked["no_trade_now"])
        self.assertIn("baixa liquidez", blocked["no_trade_reasons"])

    def test_risk_high_and_low_consume_risk_ia(self):
        low = _panel(tools=_bullish_tools(risk_state="low_risk", risk_score=22))
        high = _panel(tools=_bullish_tools(risk_state="high_risk", risk_score=88))

        self.assertEqual(low["risk_block"]["level"], "Baixo")
        self.assertEqual(high["risk_block"]["level"], "Alto")
        self.assertEqual(high["recommended_action"], ACTION_WAIT)

    def test_snapshot_propagates_strategic_panel(self):
        payload = build_snapshot_payload([_row()], source="test")
        signal = payload["signals"][0]

        self.assertIn("strategic_panel", payload)
        self.assertIn("strategic_panel_summary", payload)
        self.assertIn("strategic_panel", signal)
        self.assertEqual(signal["strategic_panel"]["ticker"], signal["ticker"])
        self.assertEqual(signal["strategic_panel_summary"], signal["strategic_panel"]["strategic_panel_summary"])

    def test_workspace_consumes_strategic_panel(self):
        panel = _panel()
        signal = {
            **_row(),
            "master_score": 84.0,
            "master_direction": "BULLISH",
            "master_status": "APPROVED",
            "strategic_panel": panel,
            "strategic_panel_summary": panel["strategic_panel_summary"],
            "recommended_action": panel["recommended_action"],
        }
        snapshot = {
            "signals": [signal],
            "ai_tools": workspace_service._empty_ai_outputs(),
            "master_score": signal,
            "master_scores": [signal],
            "strategic_panel": panel,
            "strategic_panels": [panel],
            "strategic_panel_summary": panel["strategic_panel_summary"],
        }
        bootstrap = {"brand": "StockNewsBR", "pricing": {"trial_days": 30}, "launch_roadmap": {}, "ai_modules": [], "social_features": {}}
        metrics = {"engine_cycles": 1, "signals_generated": 1, "assets_scanned": 1, "cache_age": 0, "http_requests": 0, "ws_connections": 0, "chat_messages": 0}
        with patch.object(workspace_service, "get_public_bootstrap", return_value=bootstrap), patch.object(
            workspace_service, "get_metrics_snapshot", return_value=metrics
        ), patch.object(workspace_service, "get_snapshot", return_value=snapshot), patch.object(
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

        self.assertEqual(payload["strategic_panel"]["ticker"], "PETR4")
        self.assertEqual(payload["market_snapshot"]["strategic_panel"]["ticker"], "PETR4")
        self.assertEqual(payload["top_signals"][0]["strategic_panel"]["recommended_action"], panel["recommended_action"])

    def test_public_insight_exposes_strategic_panel_contract(self):
        panel = _panel()
        row = {
            **_row(),
            "master_score": 83.0,
            "master_direction": "BULLISH",
            "master_status": "APPROVED",
            "strategic_panel": panel,
            "strategic_panel_summary": panel["strategic_panel_summary"],
            "recommended_action": panel["recommended_action"],
        }
        with patch.object(routes_public_market_live, "get_snapshot_ticker", return_value=row), patch.object(
            routes_public_market_live, "_load_chart_data_fast", return_value=[]
        ):
            payload = routes_public_market_live.public_market_insight("PETR4")

        self.assertEqual(payload["strategic_panel"]["recommended_action"], panel["recommended_action"])
        self.assertEqual(payload["strategic_panel_summary"], panel["strategic_panel_summary"])


if __name__ == "__main__":
    unittest.main()
