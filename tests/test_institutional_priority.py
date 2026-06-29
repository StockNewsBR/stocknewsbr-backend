import unittest
from unittest.mock import patch

from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED, AUDIT_CAUTION
from app.ai.institutional_priority import (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    enrich_institutional_priority_rows,
    priority_items,
)
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
        "audit_blocks": ["baixa liquidez"] if audit_status == AUDIT_BLOCKED else [],
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
    }
    row.update(overrides)
    row.setdefault("score_source_scale", "0_100")
    if row.get("master_score_source_scale") == "0_10":
        display_value = float(row.get("master_score") or 0.0)
        if "master_score_raw" not in row:
            row["master_score_raw"] = display_value if display_value > 10.0 else display_value * 10.0
        if display_value > 10.0:
            row["master_score"] = round(display_value / 10.0, 1)
        if "score_source_scale" not in overrides:
            row["score_source_scale"] = "0_10"
        if "ranking_opportunity_source_scale" not in overrides:
            row["ranking_opportunity_source_scale"] = "0_10"
    else:
        row.setdefault("master_score_raw", row.get("master_score"))
        row.setdefault("master_score_source_scale", "0_100")
    row.setdefault("ranking_opportunity_source_scale", "0_100")
    for score_key, scale_key in (("score", "score_source_scale"), ("ranking_opportunity_score", "ranking_opportunity_source_scale")):
        if row.get(scale_key) == "0_10" and score_key in row:
            score_value = float(row.get(score_key) or 0.0)
            if score_value > 10.0:
                row[score_key] = round(score_value / 10.0, 1)
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


class InstitutionalPriorityTests(unittest.TestCase):
    def test_priority_levels_critical_high_medium_and_low(self):
        rows, _ = enrich_institutional_priority_rows(
            [
                _row("CRIT1"),
                _row(
                    "HIGH1",
                    radar_prioritization_score=76.0,
                    ranking_opportunity_score=76.0,
                    conviction_score=74.0,
                    conviction_level="🟢 ALTA",
                    historical_confidence_score=55.0,
                    historical_confidence_label="🟡 Confiança Histórica Moderada",
                    operational_score=78.0,
                    audit_score=88.0,
                    ranking_classification="🥈 Forte",
                ),
                _row(
                    "MED1",
                    radar_prioritization_score=45.0,
                    ranking_opportunity_score=52.0,
                    conviction_score=58.0,
                    conviction_level="🟡 MODERADA",
                    historical_confidence_score=0.0,
                    historical_confidence_label="⚪ Amostra Insuficiente",
                    operational_score=64.0,
                    audit_score=70.0,
                    radar_level="⚪ OBSERVAÇÃO",
                    radar_priority="⚪ OBSERVAÇÃO",
                    ranking_classification="⚪ Observação",
                ),
                _row(
                    "LOW1",
                    audit_status=AUDIT_CAUTION,
                    master_status=AUDIT_CAUTION,
                    radar_prioritization_score=20.0,
                    ranking_opportunity_score=30.0,
                    conviction_score=28.0,
                    conviction_level="🔴 BAIXA",
                    historical_confidence_score=20.0,
                    historical_confidence_label="🔴 Baixa Confiança Histórica",
                    operational_status="CAUTION",
                    operational_ready=False,
                    operational_score=44.0,
                    master_risk="Alto",
                ),
            ],
            ai_tools=_risk_tool("LOW1", score=78, state="high_risk"),
            market_pulse={"sentiment": "neutral"},
        )
        by_ticker = {row["ticker"]: row for row in rows}

        self.assertEqual(by_ticker["CRIT1"]["priority_level"], PRIORITY_CRITICAL)
        self.assertEqual(by_ticker["HIGH1"]["priority_level"], PRIORITY_HIGH)
        self.assertEqual(by_ticker["MED1"]["priority_level"], PRIORITY_MEDIUM)
        self.assertEqual(by_ticker["LOW1"]["priority_level"], PRIORITY_LOW)
        self.assertIn("priority_summary", by_ticker["CRIT1"])

    def test_operational_block_forces_low_priority_without_rank(self):
        rows, _ = enrich_institutional_priority_rows(
            [
                _row(
                    "BLOQ1",
                    operational_status="BLOCKED",
                    operational_ready=False,
                    operational_score=0.0,
                    operational_blocks=["data quality stale"],
                    ranking_eligible=False,
                    master_score=99.0,
                    conviction_score=99.0,
                )
            ],
            ai_tools=_risk_tool("BLOQ1"),
        )

        self.assertEqual(rows[0]["priority_score"], 0.0)
        self.assertEqual(rows[0]["priority_level"], PRIORITY_LOW)
        self.assertIsNone(rows[0]["priority_rank"])
        self.assertIn("data quality stale", rows[0]["priority_factors"])

    def test_conviction_and_history_change_priority_score(self):
        strong, _ = enrich_institutional_priority_rows([_row("STRONG")], ai_tools=_risk_tool("STRONG"))
        weak, _ = enrich_institutional_priority_rows(
            [
                _row(
                    "WEAK",
                    conviction_score=35.0,
                    conviction_level="🔴 BAIXA",
                    historical_confidence_score=20.0,
                    historical_confidence_label="🔴 Baixa Confiança Histórica",
                    ranking_classification="🥉 Moderada",
                    radar_level="⚪ OBSERVAÇÃO",
                    radar_priority="⚪ OBSERVAÇÃO",
                )
            ],
            ai_tools=_risk_tool("WEAK", score=72, state="high_risk"),
            market_pulse={"sentiment": "neutral"},
        )

        self.assertGreater(strong[0]["priority_score"], weak[0]["priority_score"])
        self.assertIn("Convicção muito alta", strong[0]["priority_factors"])
        self.assertIn("histórico fraco", weak[0]["priority_factors"])

    def test_priority_rank_orders_eligible_assets(self):
        rows, _ = enrich_institutional_priority_rows(
            [
                _row(
                    "SECOND",
                    radar_prioritization_score=70.0,
                    ranking_opportunity_score=70.0,
                    conviction_score=72.0,
                    conviction_level="🟢 ALTA",
                    historical_confidence_score=55.0,
                    historical_confidence_label="🟡 Confiança Histórica Moderada",
                    operational_score=76.0,
                    audit_score=86.0,
                    radar_level="⚪ OBSERVAÇÃO",
                    radar_priority="⚪ OBSERVAÇÃO",
                    ranking_classification="🥈 Forte",
                ),
                _row("FIRST"),
                _row("BLOCKED", operational_status="BLOCKED", operational_ready=False, operational_blocks=["bloqueado"]),
            ],
            ai_tools=_risk_tool("FIRST"),
        )
        queue = priority_items(rows, limit=10)

        self.assertEqual(queue[0]["ticker"], "FIRST")
        self.assertEqual(queue[0]["priority_rank"], 1)
        self.assertNotIn("BLOCKED", [row["ticker"] for row in queue])

    def test_snapshot_propagates_priority_to_contracts(self):
        with patch("app.engine.market_snapshot_engine.build_ai_payload_bundle", return_value={"ai_tools": _bullish_tools(), "internal_engine_keys": []}), patch(
            "app.ai.historical_confidence.get_history",
            return_value=_history("PETR4"),
        ):
            payload = build_snapshot_payload([_row("PETR4")], source="test")

        signal = payload["signals"][0]
        self.assertIn("institutional_priorities", payload)
        self.assertIn("priority_metrics", payload)
        self.assertIn("priority_score", signal)
        self.assertIn("priority_score", payload["master_score"])
        self.assertIn("priority_score", payload["strategic_panel"])

    def test_workspace_ranking_radar_and_public_api_consume_priority(self):
        enriched, _ = enrich_institutional_priority_rows(
            [_row("PETR4"), _row("VALE3", radar_prioritization_score=64.0, ranking_opportunity_score=68.0, conviction_score=70.0, conviction_level="🟢 ALTA")],
            ai_tools=_risk_tool("PETR4"),
            market_pulse={"sentiment": "bullish"},
        )
        snapshot = {
            "signals": enriched,
            "ai_tools": workspace_service._empty_ai_outputs(),
            "market_pulse": {"sentiment": "bullish"},
            "institutional_radar": institutional_radar_items(enriched, limit=20),
            "institutional_ranking": enriched,
            "institutional_priorities": priority_items(enriched, limit=20),
            "priority_metrics": {"critical": 1, "high": 1, "medium": 0, "low": 0},
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

        self.assertIn("priority_score", ranked[0])
        self.assertIn("priority_score", institutional_radar_items(enriched, limit=20)[0])
        self.assertEqual(payload["institutional_priorities"][0]["ticker"], "PETR4")
        self.assertEqual(payload["market_snapshot"]["priority_metrics"]["critical"], 1)
        self.assertEqual(insight["priority_level"], enriched[0]["priority_level"])

    def test_metrics_record_priority_levels(self):
        enrich_institutional_priority_rows(
            [
                _row("CRITM"),
                _row(
                    "HIGHM",
                    radar_prioritization_score=76.0,
                    ranking_opportunity_score=76.0,
                    conviction_score=74.0,
                    conviction_level="🟢 ALTA",
                    historical_confidence_score=55.0,
                    historical_confidence_label="🟡 Confiança Histórica Moderada",
                    operational_score=70.0,
                    audit_score=80.0,
                    ranking_classification="🥈 Forte",
                    radar_level="⚪ OBSERVAÇÃO",
                    radar_priority="⚪ OBSERVAÇÃO",
                ),
                _row(
                    "MEDM",
                    radar_prioritization_score=45.0,
                    ranking_opportunity_score=52.0,
                    conviction_score=58.0,
                    conviction_level="🟡 MODERADA",
                    historical_confidence_score=0.0,
                    historical_confidence_label="⚪ Amostra Insuficiente",
                    operational_score=64.0,
                    audit_score=70.0,
                    radar_level="⚪ OBSERVAÇÃO",
                    radar_priority="⚪ OBSERVAÇÃO",
                    ranking_classification="⚪ Observação",
                ),
                _row("LOWM", operational_status="BLOCKED", operational_ready=False, operational_blocks=["bloqueado"]),
            ],
            ai_tools=_risk_tool("CRITM"),
            record_metrics=True,
        )

        metrics = get_performance_metrics_snapshot()["institutional_priority"]
        self.assertGreaterEqual(metrics["critical"], 1)
        self.assertGreaterEqual(metrics["high"], 1)
        self.assertGreaterEqual(metrics["medium"], 1)
        self.assertGreaterEqual(metrics["low"], 1)


if __name__ == "__main__":
    unittest.main()
