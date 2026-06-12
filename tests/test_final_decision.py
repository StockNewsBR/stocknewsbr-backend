import unittest
from unittest.mock import patch

from app.ai.final_decision import (
    FINAL_CONFIRMED,
    FINAL_FORMING,
    FINAL_NO_TRADE,
    FINAL_OBSERVE,
    FINAL_WAIT,
    enrich_final_decision_rows,
    final_decision_items,
)
from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED, AUDIT_CAUTION
from app.ai.institutional_radar import institutional_radar_items
from app.api import routes_public_market_live
from app.engine.market_snapshot_engine import build_snapshot_payload
from app.services import ranking, workspace_service
from app.system.system_metrics import get_performance_metrics_snapshot


def _row(ticker="PETR4", audit_status=AUDIT_APPROVED, **overrides):
    row = {
        "ticker": ticker,
        "symbol": ticker,
        "score": 92.0,
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
        "audit_status": audit_status,
        "auditor_status": audit_status,
        "audit_score": 94.0 if audit_status == AUDIT_APPROVED else 68.0 if audit_status == AUDIT_CAUTION else 20.0,
        "audit_confidence": "Alta",
        "audit_blocks": ["auditor bloqueado"] if audit_status == AUDIT_BLOCKED else [],
        "audit_warnings": ["conflito leve"] if audit_status == AUDIT_CAUTION else [],
        "audit_summary": f"{ticker}: {audit_status}",
        "blocked_by_auditor": audit_status == AUDIT_BLOCKED,
        "master_score": 92.0,
        "master_direction": "BULLISH",
        "master_conviction": "Alta",
        "master_confidence": "Alta",
        "master_status": audit_status,
        "master_risk": "Baixo",
        "master_summary": "Fluxo comprador, smart money positivo e liquidez adequada.",
        "master_reasoning": {"flow_reason": "Fluxo comprador", "smart_money_reason": "Smart Money positivo"},
        "master_consensus": {"aligned_count": 7, "opposing_count": 1, "ratio": 0.78, "total": 9},
        "strategic_panel": {
            "recommended_action": "OPORTUNIDADE CONFIRMADA",
            "strategic_panel_summary": "Fluxo comprador e Auditor aprovado. Risco baixo.",
            "no_trade_now": False,
            "risk_block": {"level": "Baixo", "source": "risk_ia", "score": 22},
        },
        "strategic_panel_summary": "Fluxo comprador e Auditor aprovado. Risco baixo.",
        "recommended_action": "OPORTUNIDADE CONFIRMADA",
        "radar_prioritization_score": 94.0,
        "radar_priority_score": 94.0,
        "radar_priority": "🔥 PRIORIDADE ALTA",
        "radar_level": "🔥 PRIORIDADE ALTA",
        "radar_reason": "Fluxo comprador, Smart Money positivo e Auditor aprovado.",
        "radar_summary": "Radar em prioridade alta.",
        "radar_no_trade_now": False,
        "radar_blocked_reasons": [],
        "ranking_opportunity_score": 94.0,
        "ranking_classification": "🥇 Excelente",
        "ranking_eligible": True,
        "historical_confidence_score": 86.0,
        "historical_confidence_label": "🟢 Alta Confiança Histórica",
        "historical_sample_size": 24,
        "historical_win_rate": 82.0,
        "historical_context_match": 88.0,
        "historical_reason": "Leituras semelhantes tiveram bom desempenho.",
        "historical_warning": "",
        "operational_status": "READY",
        "operational_ready": True,
        "operational_score": 92.0,
        "operational_blocks": [],
        "operational_warnings": [],
        "operational_summary": "Condições mínimas presentes.",
        "conviction_score": 96.0,
        "conviction_level": "🔥 MUITO ALTA",
        "conviction_summary": "Evidência institucional muito alinhada.",
        "conviction_factors": ["consenso institucional", "auditor aprovado"],
        "conviction_conflicts": [],
        "priority_score": 96.0,
        "priority_level": "🚨 CRÍTICA",
        "priority_rank": 1,
        "priority_summary": "Prioridade crítica por alinhamento institucional.",
        "priority_factors": ["Radar prioridade alta", "Convicção muito alta"],
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


def _history(ticker="PETR4", wins=9, losses=1):
    return [{**_row(ticker), "historical_result": "win" if index < wins else "loss"} for index in range(wins + losses)]


class FinalDecisionTests(unittest.TestCase):
    def test_final_decision_levels(self):
        rows, _ = enrich_final_decision_rows(
            [
                _row("CONF1"),
                _row(
                    "FORM1",
                    priority_score=68.0,
                    priority_level="🟡 MÉDIA",
                    ranking_opportunity_score=80.0,
                    ranking_classification="🥈 Forte",
                    conviction_score=80.0,
                    conviction_level="🟢 ALTA",
                    historical_confidence_score=50.0,
                ),
                _row(
                    "OBS1",
                    audit_status=AUDIT_CAUTION,
                    master_status=AUDIT_CAUTION,
                    operational_status="CAUTION",
                    operational_ready=False,
                    operational_score=48.0,
                    conviction_score=38.0,
                    conviction_level="🔴 BAIXA",
                    conviction_conflicts=["consenso institucional baixo"],
                    priority_score=38.0,
                    priority_level="⚪ BAIXA",
                    ranking_opportunity_score=42.0,
                    ranking_classification="⚪ Observação",
                    radar_prioritization_score=42.0,
                    radar_level="⚪ OBSERVAÇÃO",
                    master_risk="Alto",
                ),
                _row(
                    "WAIT1",
                    priority_score=25.0,
                    priority_level="⚪ BAIXA",
                    ranking_opportunity_score=35.0,
                    ranking_classification="⚪ Observação",
                    conviction_score=45.0,
                    conviction_level="🟡 MODERADA",
                    historical_confidence_score=0.0,
                    historical_confidence_label="⚪ Amostra Insuficiente",
                    radar_prioritization_score=35.0,
                    radar_level="⚪ OBSERVAÇÃO",
                    operational_score=65.0,
                    audit_score=80.0,
                    master_confidence="Média",
                    master_consensus={},
                ),
                _row("NOOP1", decision_ready=False),
            ],
            ai_tools=_risk_tool("OBS1", score=74, state="high_risk"),
            market_pulse={"sentiment": "neutral"},
        )
        by_ticker = {row["ticker"]: row for row in rows}

        self.assertEqual(by_ticker["CONF1"]["final_decision"], FINAL_CONFIRMED)
        self.assertEqual(by_ticker["FORM1"]["final_decision"], FINAL_FORMING)
        self.assertEqual(by_ticker["OBS1"]["final_decision"], FINAL_OBSERVE)
        self.assertEqual(by_ticker["WAIT1"]["final_decision"], FINAL_WAIT)
        self.assertEqual(by_ticker["NOOP1"]["final_decision"], FINAL_NO_TRADE)
        self.assertIn("final_decision_summary", by_ticker["CONF1"])

    def test_auditor_and_operational_block_force_no_trade(self):
        rows, _ = enrich_final_decision_rows(
            [
                _row("AUD1", audit_status=AUDIT_BLOCKED, master_status=AUDIT_BLOCKED),
                _row(
                    "OPR1",
                    operational_status="BLOCKED",
                    operational_ready=False,
                    operational_score=0.0,
                    operational_blocks=["data quality stale"],
                ),
            ],
            ai_tools=_risk_tool("AUD1"),
        )

        self.assertTrue(all(row["final_decision"] == FINAL_NO_TRADE for row in rows))
        self.assertIn("auditor bloqueado", rows[0]["final_decision_blocks"])
        self.assertIn("data quality stale", rows[1]["final_decision_blocks"])

    def test_conviction_and_priority_drive_confirmed_decision(self):
        confirmed, _ = enrich_final_decision_rows([_row("STRONG")], ai_tools=_risk_tool("STRONG"))
        weak, _ = enrich_final_decision_rows(
            [
                _row(
                    "WEAK",
                    conviction_score=42.0,
                    conviction_level="🟡 MODERADA",
                    priority_score=42.0,
                    priority_level="⚪ BAIXA",
                    ranking_opportunity_score=45.0,
                    ranking_classification="⚪ Observação",
                    radar_prioritization_score=42.0,
                    radar_level="⚪ OBSERVAÇÃO",
                    historical_confidence_score=0.0,
                )
            ],
            ai_tools=_risk_tool("WEAK"),
        )

        self.assertEqual(confirmed[0]["final_decision"], FINAL_CONFIRMED)
        self.assertGreater(confirmed[0]["final_decision_score"], weak[0]["final_decision_score"])
        self.assertIn("Auditor aprovado", confirmed[0]["final_decision_reason"])

    def test_snapshot_propagates_final_decision_contract(self):
        with patch("app.engine.market_snapshot_engine.build_ai_payload_bundle", return_value={"ai_tools": _bullish_tools(), "internal_engine_keys": []}), patch(
            "app.ai.historical_confidence.get_history",
            return_value=_history("PETR4"),
        ):
            payload = build_snapshot_payload([_row("PETR4")], source="test")

        signal = payload["signals"][0]
        self.assertIn("final_decisions", payload)
        self.assertIn("final_decision_metrics", payload)
        self.assertIn("final_decision", signal)
        self.assertIn("final_decision_score", signal)
        self.assertIn("final_decision_confidence", signal)

    def test_workspace_ranking_radar_and_public_api_consume_final_decision(self):
        enriched, _ = enrich_final_decision_rows(
            [_row("PETR4"), _row("VALE3", priority_score=70.0, priority_level="🔥 ALTA", conviction_score=70.0, conviction_level="🟢 ALTA")],
            ai_tools=_risk_tool("PETR4"),
            market_pulse={"sentiment": "bullish"},
        )
        snapshot = {
            "signals": enriched,
            "ai_tools": workspace_service._empty_ai_outputs(),
            "market_pulse": {"sentiment": "bullish"},
            "institutional_radar": institutional_radar_items(enriched, limit=20),
            "institutional_ranking": enriched,
            "final_decisions": final_decision_items(enriched, limit=20),
            "final_decision_metrics": {"confirmed": 1, "forming": 1, "observe": 0, "wait": 0, "no_trade": 0},
        }
        bootstrap = {"brand": "StockNewsBR", "pricing": {"trial_days": 30}, "launch_roadmap": {}, "ai_modules": [], "social_features": {}}
        metrics = {"engine_cycles": 1, "signals_generated": 2, "assets_scanned": 2, "cache_age": 0, "http_requests": 0, "ws_connections": 0, "chat_messages": 0}

        with patch.object(ranking, "get_snapshot_info", return_value={"signals": 2, "age_seconds": 0, "timestamp": 1, "has_signals": True, "is_empty": False}), patch.object(
            ranking, "get_snapshot_signals", return_value=enriched
        ):
            ranked = ranking.get_ranking(force_refresh=True)

        with patch.object(workspace_service, "get_public_bootstrap", return_value=bootstrap), patch.object(
            workspace_service, "get_metrics_snapshot", return_value=metrics
        ), patch.object(workspace_service, "get_snapshot", return_value=snapshot), patch.object(
            workspace_service, "get_ranking", return_value=ranked
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

        with patch.object(routes_public_market_live, "get_snapshot_ticker", return_value=enriched[0]), patch.object(
            routes_public_market_live, "_load_chart_data_fast", return_value=[]
        ):
            insight = routes_public_market_live.public_market_insight("PETR4")

        self.assertIn("final_decision", ranked[0])
        self.assertIn("final_decision", institutional_radar_items(enriched, limit=20)[0])
        self.assertEqual(payload["final_decisions"][0]["ticker"], "PETR4")
        self.assertEqual(payload["market_snapshot"]["final_decision_metrics"]["confirmed"], 1)
        self.assertEqual(insight["final_decision"], enriched[0]["final_decision"])

    def test_metrics_record_final_decision_buckets(self):
        enrich_final_decision_rows(
            [
                _row("CONF"),
                _row("FORM", priority_score=68.0, priority_level="🟡 MÉDIA", ranking_opportunity_score=80.0, ranking_classification="🥈 Forte", conviction_score=80.0, conviction_level="🟢 ALTA"),
                _row(
                    "OBS",
                    audit_status=AUDIT_CAUTION,
                    master_status=AUDIT_CAUTION,
                    operational_status="CAUTION",
                    operational_ready=False,
                    operational_score=45.0,
                    conviction_score=35.0,
                    conviction_level="🔴 BAIXA",
                    conviction_conflicts=["consenso institucional baixo"],
                    priority_score=35.0,
                    priority_level="⚪ BAIXA",
                    ranking_opportunity_score=35.0,
                    ranking_classification="⚪ Observação",
                    radar_prioritization_score=35.0,
                    radar_level="⚪ OBSERVAÇÃO",
                    historical_confidence_score=20.0,
                    historical_confidence_label="🔴 Baixa Confiança Histórica",
                ),
                _row("WAIT", priority_score=20.0, priority_level="⚪ BAIXA", ranking_opportunity_score=30.0, ranking_classification="⚪ Observação", conviction_score=45.0, conviction_level="🟡 MODERADA", historical_confidence_score=0.0, radar_prioritization_score=30.0, radar_level="⚪ OBSERVAÇÃO", master_consensus={}),
                _row("NOOP", decision_ready=False),
            ],
            ai_tools=_risk_tool("CONF"),
            record_metrics=True,
        )

        metrics = get_performance_metrics_snapshot()["final_decision"]
        self.assertGreaterEqual(metrics["confirmed"], 1)
        self.assertGreaterEqual(metrics["forming"], 1)
        self.assertGreaterEqual(metrics["observe"], 1)
        self.assertGreaterEqual(metrics["wait"], 1)
        self.assertGreaterEqual(metrics["no_trade"], 1)


if __name__ == "__main__":
    unittest.main()
