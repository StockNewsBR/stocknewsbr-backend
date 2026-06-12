import unittest
from unittest.mock import patch

from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED, AUDIT_CAUTION
from app.ai.institutional_radar import institutional_radar_items
from app.ai.institutional_ranking import institutional_ranking_items
from app.ai.operational_rules import (
    OPERATIONAL_BLOCKED,
    OPERATIONAL_CAUTION,
    OPERATIONAL_READY,
    enrich_operational_rules_rows,
)
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
        "audit_blocks": ["baixa liquidez"] if audit_status == AUDIT_BLOCKED else [],
        "audit_warnings": ["conflito leve"] if audit_status == AUDIT_CAUTION else [],
        "audit_summary": f"{ticker}: {audit_status}",
        "blocked_by_auditor": audit_status == AUDIT_BLOCKED,
        "master_score": 90.0,
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
        "radar_prioritization_score": 88.0,
        "radar_level": "🔥 PRIORIDADE ALTA",
        "radar_no_trade_now": False,
        "radar_blocked_reasons": [],
        "ranking_opportunity_score": 91.0,
        "ranking_classification": "🥇 Excelente",
        "ranking_eligible": True,
        "historical_confidence_score": 82.0,
        "historical_confidence_label": "🟢 Alta Confiança Histórica",
        "historical_sample_size": 24,
        "historical_win_rate": 80.0,
        "historical_context_match": 88.0,
        "historical_reason": "Leituras semelhantes tiveram bom desempenho.",
        "historical_warning": "",
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


def _history(ticker="PETR4", wins=9, losses=1):
    rows = []
    for index in range(wins + losses):
        rows.append({**_row(ticker), "historical_result": "win" if index < wins else "loss"})
    return rows


def _bullish_tools(ticker="PETR4"):
    def tool(name, score, state, comment):
        return {"ticker": ticker, "tool": name, "score": score, "state": state, "ai_comment": comment, "metrics": {f"{name}_score": score}}

    return {
        "flow": [tool("flow", 88, "institutional_buying", "fluxo comprador bull")],
        "liquidity": [tool("liquidity", 78, "liquidity_zone", "liquidez adequada")],
        "trend": [tool("trend", 86, "uptrend_structure", "tendencia de alta")],
        "momentum": [tool("momentum", 82, "momentum_expansion", "momentum comprador")],
        "smart_money": [tool("smart_money", 87, "institutional_accumulation", "smart money acumulando")],
        "risk": [_risk_tool(ticker)["risk"][0]],
        "news": [tool("news", 64, "news_available", "noticia positiva")],
        "macro": [tool("macro", 58, "macro_context_available", "macro positivo")],
        "regime": [tool("regime", 84, "bull_trend", "regime favoravel")],
    }


class OperationalRulesTests(unittest.TestCase):
    def test_ready_caution_and_blocked_statuses(self):
        ready, _ = enrich_operational_rules_rows([_row("READY1")], ai_tools=_risk_tool("READY1"), market_pulse={"sentiment": "bullish"})
        caution, _ = enrich_operational_rules_rows(
            [
                _row(
                    "CAUT1",
                    audit_status=AUDIT_CAUTION,
                    master_status=AUDIT_CAUTION,
                    master_confidence="Baixa",
                    master_consensus={"aligned_count": 3, "opposing_count": 4, "ratio": 0.33, "total": 9},
                    historical_sample_size=3,
                    historical_confidence_label="⚪ Amostra Insuficiente",
                    master_risk="Alto",
                )
            ],
            ai_tools=_risk_tool("CAUT1", score=78, state="high_risk"),
            market_pulse={"sentiment": "neutral"},
        )
        blocked, _ = enrich_operational_rules_rows([_row("BLOQ1", audit_status=AUDIT_BLOCKED)], ai_tools=_risk_tool("BLOQ1"))

        self.assertEqual(ready[0]["operational_status"], OPERATIONAL_READY)
        self.assertTrue(ready[0]["operational_ready"])
        self.assertEqual(caution[0]["operational_status"], OPERATIONAL_CAUTION)
        self.assertFalse(caution[0]["operational_ready"])
        self.assertIn("confiança baixa", caution[0]["operational_warnings"])
        self.assertIn("consenso baixo", caution[0]["operational_warnings"])
        self.assertEqual(blocked[0]["operational_status"], OPERATIONAL_BLOCKED)
        self.assertFalse(blocked[0]["operational_ready"])

    def test_blocks_high_score_when_minimum_conditions_fail(self):
        rows, _ = enrich_operational_rules_rows(
            [
                _row(
                    "HIGH1",
                    master_score=99.0,
                    ranking_opportunity_score=98.0,
                    radar_prioritization_score=96.0,
                    decision_ready=False,
                    data_quality="score_only",
                    radar_no_trade_now=True,
                    radar_blocked_reasons=["radar bloqueou"],
                )
            ],
            ai_tools=_risk_tool("HIGH1"),
        )

        self.assertEqual(rows[0]["operational_status"], OPERATIONAL_BLOCKED)
        self.assertEqual(rows[0]["operational_score"], 0.0)
        self.assertIn("decision_ready falso", rows[0]["operational_blocks"])
        self.assertIn("data quality score_only", rows[0]["operational_blocks"])
        self.assertIn("radar bloqueou", rows[0]["operational_blocks"])

    def test_critical_risk_blocks_and_high_risk_cautions(self):
        critical, _ = enrich_operational_rules_rows([_row("CRIT1", master_risk="Crítico")], ai_tools=_risk_tool("CRIT1", score=90, state="critical_risk"))
        high, _ = enrich_operational_rules_rows([_row("RISK1", master_risk="Alto")], ai_tools=_risk_tool("RISK1", score=75, state="high_risk"))

        self.assertEqual(critical[0]["operational_status"], OPERATIONAL_BLOCKED)
        self.assertIn("risco critico", critical[0]["operational_blocks"])
        self.assertEqual(high[0]["operational_status"], OPERATIONAL_CAUTION)
        self.assertIn("risco alto", high[0]["operational_warnings"])

    def test_snapshot_propagates_operational_rules_to_contracts(self):
        with patch("app.engine.market_snapshot_engine.build_ai_payload_bundle", return_value={"ai_tools": _bullish_tools(), "internal_engine_keys": []}), patch(
            "app.ai.historical_confidence.get_history",
            return_value=_history("PETR4"),
        ):
            payload = build_snapshot_payload([_row("PETR4")], source="test")

        signal = payload["signals"][0]
        self.assertIn("operational_rules", payload)
        self.assertIn("operational_rules_metrics", payload)
        self.assertIn("operational_status", signal)
        self.assertIn("operational_status", payload["master_score"])
        self.assertIn("operational_status", payload["strategic_panel"])
        self.assertGreaterEqual(payload["operational_rules_metrics"]["ready"], 0)

    def test_workspace_ranking_radar_and_public_api_consume_operational_rules(self):
        enriched, _ = enrich_operational_rules_rows(
            [_row("PETR4"), _row("VALE3", master_score=70.0, ranking_opportunity_score=68.0, radar_prioritization_score=65.0)],
            ai_tools=_risk_tool("PETR4"),
            market_pulse={"sentiment": "bullish"},
        )
        snapshot = {
            "signals": enriched,
            "ai_tools": workspace_service._empty_ai_outputs(),
            "market_pulse": {"sentiment": "bullish"},
            "institutional_ranking": institutional_ranking_items(enriched, limit=20),
            "institutional_radar": institutional_radar_items(enriched, limit=20),
            "operational_rules": enriched,
            "operational_rules_metrics": {"ready": 2, "caution": 0, "blocked": 0},
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

        self.assertIn("operational_status", ranked[0])
        self.assertIn("operational_status", institutional_radar_items(enriched, limit=20)[0])
        self.assertEqual(payload["operational_rules"][0]["ticker"], "PETR4")
        self.assertEqual(payload["market_snapshot"]["operational_rules_metrics"]["ready"], 2)
        self.assertEqual(insight["operational_status"], enriched[0]["operational_status"])

    def test_metrics_record_statuses_blocks_and_warnings(self):
        enrich_operational_rules_rows(
            [
                _row("READY1"),
                _row("CAUT1", master_confidence="Baixa"),
                _row("BLOQ1", audit_status=AUDIT_BLOCKED),
            ],
            ai_tools=_risk_tool("READY1"),
            market_pulse={"sentiment": "bullish"},
            record_metrics=True,
        )

        metrics = get_performance_metrics_snapshot()["operational_rules"]
        self.assertEqual(metrics["ready"], 1)
        self.assertEqual(metrics["caution"], 1)
        self.assertEqual(metrics["blocked"], 1)
        self.assertIn("baixa liquidez", metrics["top_blocks"])
        self.assertIn("confiança baixa", metrics["top_warnings"])


if __name__ == "__main__":
    unittest.main()
