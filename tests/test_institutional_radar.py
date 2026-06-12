import unittest
from unittest.mock import patch

from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED, AUDIT_CAUTION
from app.ai.institutional_radar import (
    RADAR_LEVEL_HIGH,
    RADAR_LEVEL_MEDIUM,
    RADAR_LEVEL_NO_TRADE,
    enrich_institutional_radar_rows,
)
from app.api import routes_public_market_live
from app.engine.market_snapshot_engine import build_snapshot_payload
from app.services import workspace_service
from app.system.system_metrics import get_performance_metrics_snapshot
from app.web import routes_radar as web_radar


def _row(ticker="PETR4", audit_status=AUDIT_APPROVED, **overrides):
    row = {
        "ticker": ticker,
        "symbol": ticker,
        "score": 91.0,
        "signal": "BUY",
        "trade_action": "BUY",
        "decision_ready": True,
        "decision_state": "BUY_READY",
        "can_trade": True,
        "data_quality": "cached",
        "price": 37.5,
        "volume": 1_800_000,
        "avg_volume": 900_000,
        "rel_volume": 2.0,
        "momentum": 1.8,
        "change_pct": 1.5,
        "trend_strength": 76.0,
        "atr_pct": 1.4,
        "audit_status": audit_status,
        "auditor_status": audit_status,
        "audit_score": 92.0 if audit_status == AUDIT_APPROVED else 68.0 if audit_status == AUDIT_CAUTION else 20.0,
        "audit_confidence": "Alta",
        "audit_blocks": ["baixa liquidez"] if audit_status == AUDIT_BLOCKED else [],
        "audit_warnings": ["conflito leve"] if audit_status == AUDIT_CAUTION else [],
        "audit_summary": f"{ticker}: {audit_status}",
        "blocked_by_auditor": audit_status == AUDIT_BLOCKED,
        "master_score": 88.0,
        "master_direction": "BULLISH",
        "master_conviction": "Alta",
        "master_confidence": "Alta",
        "master_status": audit_status,
        "master_risk": "Baixo",
        "master_summary": "Fluxo comprador, smart money positivo e liquidez adequada.",
        "master_reasoning": {
            "flow_reason": "Fluxo comprador institucional.",
            "smart_money_reason": "Smart Money positivo.",
            "liquidity_reason": "Liquidez adequada.",
        },
        "master_consensus": {"aligned_count": 7, "opposing_count": 1, "ratio": 0.78, "total": 9},
        "strategic_panel": {
            "recommended_action": "OPORTUNIDADE CONFIRMADA",
            "strategic_panel_summary": "Fluxo comprador e Auditor aprovado. Risco baixo.",
            "no_trade_now": False,
            "risk_block": {"level": "Baixo", "source": "risk_ia", "score": 22},
        },
        "strategic_panel_summary": "Fluxo comprador e Auditor aprovado. Risco baixo.",
        "recommended_action": "OPORTUNIDADE CONFIRMADA",
    }
    row.update(overrides)
    return row


def _risk_tool(ticker="PETR4", score=22, state="low_risk"):
    return {
        "risk": [
            {
                "ticker": ticker,
                "tool": "risk",
                "score": score,
                "state": state,
                "ai_comment": state,
                "metrics": {"risk_score": score, "risk_summary": state},
            }
        ]
    }


def _bullish_tools(ticker="PETR4", risk_score=22, risk_state="low_risk"):
    def tool(name, score, state, comment):
        return {"ticker": ticker, "tool": name, "score": score, "state": state, "ai_comment": comment, "metrics": {f"{name}_score": score}}

    return {
        "flow": [tool("flow", 88, "institutional_buying", "fluxo comprador bull")],
        "liquidity": [tool("liquidity", 78, "liquidity_zone", "liquidez adequada")],
        "trend": [tool("trend", 86, "uptrend_structure", "tendencia de alta")],
        "momentum": [tool("momentum", 82, "momentum_expansion", "momentum comprador")],
        "smart_money": [tool("smart_money", 87, "institutional_accumulation", "smart money acumulando")],
        "risk": [_risk_tool(ticker, risk_score, risk_state)["risk"][0]],
        "news": [tool("news", 64, "news_available", "noticia positiva")],
        "macro": [tool("macro", 58, "macro_context_available", "macro positivo")],
        "regime": [tool("regime", 84, "bull_trend", "regime favoravel")],
    }


class InstitutionalRadarTests(unittest.TestCase):
    def test_approved_asset_gets_priority_reason_and_summary(self):
        rows, metrics = enrich_institutional_radar_rows([_row()], ai_tools=_risk_tool(), market_pulse={"sentiment": "bullish"})

        self.assertEqual(metrics["promoted"], 1)
        self.assertGreaterEqual(rows[0]["radar_prioritization_score"], 80)
        self.assertEqual(rows[0]["radar_level"], RADAR_LEVEL_HIGH)
        self.assertIn("Auditor aprovado", rows[0]["radar_reason"])
        self.assertLessEqual(len(rows[0]["radar_summary"]), 220)

    def test_blocked_asset_gets_no_trade_now_and_reasons(self):
        rows, metrics = enrich_institutional_radar_rows([_row(audit_status=AUDIT_BLOCKED)], ai_tools=_risk_tool())

        self.assertEqual(metrics["blocked"], 1)
        self.assertEqual(rows[0]["radar_level"], RADAR_LEVEL_NO_TRADE)
        self.assertTrue(rows[0]["radar_no_trade_now"])
        self.assertIn("baixa liquidez", rows[0]["radar_blocked_reasons"])

    def test_high_risk_reduces_priority_without_forcing_trade(self):
        low, _ = enrich_institutional_radar_rows([_row()], ai_tools=_risk_tool(score=22, state="low_risk"))
        high, _ = enrich_institutional_radar_rows([_row(master_risk="Alto")], ai_tools=_risk_tool(score=78, state="high_risk"))

        self.assertGreater(low[0]["radar_prioritization_score"], high[0]["radar_prioritization_score"])
        self.assertIn(high[0]["radar_level"], {RADAR_LEVEL_HIGH, RADAR_LEVEL_MEDIUM, "⚪ OBSERVAÇÃO"})

    def test_consensus_high_and_low_change_priority(self):
        strong = _row(master_consensus={"aligned_count": 7, "opposing_count": 1, "ratio": 0.78, "total": 9})
        weak = _row(master_consensus={"aligned_count": 3, "opposing_count": 4, "ratio": 0.33, "total": 9}, master_conviction="Baixa", master_confidence="Baixa")

        strong_rows, _ = enrich_institutional_radar_rows([strong], ai_tools=_risk_tool())
        weak_rows, _ = enrich_institutional_radar_rows([weak], ai_tools=_risk_tool())

        self.assertGreater(strong_rows[0]["radar_prioritization_score"], weak_rows[0]["radar_prioritization_score"])

    def test_caution_data_quality_score_only_and_stale_are_handled(self):
        caution, _ = enrich_institutional_radar_rows([_row(audit_status=AUDIT_CAUTION, master_status=AUDIT_CAUTION)], ai_tools=_risk_tool())
        score_only, _ = enrich_institutional_radar_rows([_row(data_quality="score_only", price=0, volume=0)], ai_tools=_risk_tool())
        stale, _ = enrich_institutional_radar_rows([_row(data_quality="stale", is_stale=True)], ai_tools=_risk_tool())

        self.assertLess(caution[0]["radar_prioritization_score"], _row()["master_score"])
        self.assertTrue(score_only[0]["radar_no_trade_now"])
        self.assertTrue(stale[0]["radar_no_trade_now"])
        self.assertIn("data quality score_only", score_only[0]["radar_blocked_reasons"])

    def test_snapshot_propagates_radar_contract_and_metrics(self):
        with patch("app.engine.market_snapshot_engine.build_ai_payload_bundle", return_value={"ai_tools": _bullish_tools(), "internal_engine_keys": []}):
            payload = build_snapshot_payload([_row()], source="test")

        signal = payload["signals"][0]
        self.assertIn("institutional_radar", payload)
        self.assertIn("radar_metrics", payload)
        self.assertIn("radar_prioritization_score", signal)
        self.assertIn("radar_reason", signal)
        self.assertIn("radar_summary", signal)
        self.assertGreaterEqual(payload["radar_metrics"]["promoted"], 1)

    def test_workspace_consumes_institutional_radar(self):
        enriched, _ = enrich_institutional_radar_rows([_row("PETR4"), _row("VALE3", master_score=62.0, master_conviction="Baixa")], ai_tools=_risk_tool())
        snapshot = {"signals": enriched, "ai_tools": workspace_service._empty_ai_outputs(), "institutional_radar": enriched, "radar_metrics": {"promoted": 2}}
        bootstrap = {"brand": "StockNewsBR", "pricing": {"trial_days": 30}, "launch_roadmap": {}, "ai_modules": [], "social_features": {}}
        metrics = {"engine_cycles": 1, "signals_generated": 2, "assets_scanned": 2, "cache_age": 0, "http_requests": 0, "ws_connections": 0, "chat_messages": 0}
        with patch.object(workspace_service, "get_public_bootstrap", return_value=bootstrap), patch.object(
            workspace_service, "get_metrics_snapshot", return_value=metrics
        ), patch.object(workspace_service, "get_snapshot", return_value=snapshot), patch.object(
            workspace_service, "get_ranking", return_value=[]
        ), patch.object(workspace_service, "get_posts", return_value=[]), patch.object(
            workspace_service, "get_help_center_blueprint", return_value={"guides": []}
        ), patch.object(workspace_service, "get_media_status", return_value={}), patch.object(
            workspace_service, "get_push_status", return_value={}
        ), patch.object(workspace_service.routes_system, "observability_dashboard", return_value={}), patch.object(
            workspace_service, "get_user_workspace_layout", return_value={"tabs": ["home"], "pinned_ticker": "PETR4", "opened_popouts": []}
        ), patch.object(workspace_service, "get_layout", return_value={"tabs": [{"id": "home", "title": "Home"}]}), patch.object(
            workspace_service, "list_room_messages", return_value=[]
        ), patch.object(workspace_service, "persist_ai_alert_history", side_effect=lambda value: value):
            payload = workspace_service.get_workspace_data(user_id=7, channel="web")

        self.assertEqual(payload["top_signals"][0]["ticker"], "PETR4")
        self.assertIn("radar_reason", payload["top_signals"][0])
        self.assertEqual(payload["market_snapshot"]["radar_metrics"]["promoted"], 2)

    def test_web_and_public_api_expose_radar_fields(self):
        enriched, _ = enrich_institutional_radar_rows([_row(events=["momentum"])], ai_tools=_risk_tool())
        with patch.object(web_radar, "get_snapshot_signals", return_value=enriched):
            radar_payload = web_radar.get_radar()
        with patch.object(routes_public_market_live, "get_snapshot_ticker", return_value=enriched[0]), patch.object(
            routes_public_market_live, "_load_chart_data_fast", return_value=[]
        ):
            insight = routes_public_market_live.public_market_insight("PETR4")

        self.assertEqual(radar_payload[0]["ticker"], "PETR4")
        self.assertIn("radar_summary", radar_payload[0])
        self.assertEqual(insight["radar_level"], enriched[0]["radar_level"])
        self.assertEqual(insight["radar_summary"], enriched[0]["radar_summary"])

    def test_metrics_record_generated_promoted_discarded_and_blocked(self):
        enrich_institutional_radar_rows(
            [
                _row("PETR4"),
                _row("BLOQ1", audit_status=AUDIT_BLOCKED),
                _row("WAIT1", master_score=10.0, master_conviction="Baixa", master_confidence="Baixa"),
            ],
            ai_tools=_risk_tool(),
            record_metrics=True,
        )

        metrics = get_performance_metrics_snapshot()["institutional_radar"]
        self.assertEqual(metrics["generated"], 3)
        self.assertGreaterEqual(metrics["promoted"], 1)
        self.assertGreaterEqual(metrics["blocked"], 1)
        self.assertIn("discarded", metrics)


if __name__ == "__main__":
    unittest.main()
