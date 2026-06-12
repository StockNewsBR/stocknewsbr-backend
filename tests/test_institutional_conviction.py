import unittest
from unittest.mock import patch

from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_CAUTION
from app.ai.institutional_conviction import (
    CONVICTION_HIGH,
    CONVICTION_LOW,
    CONVICTION_MODERATE,
    CONVICTION_VERY_HIGH,
    enrich_institutional_conviction_rows,
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
        "audit_status": audit_status,
        "auditor_status": audit_status,
        "audit_score": 94.0 if audit_status == AUDIT_APPROVED else 68.0,
        "audit_confidence": "Alta",
        "audit_warnings": ["atenção"] if audit_status == AUDIT_CAUTION else [],
        "blocked_by_auditor": False,
        "master_score": 90.0,
        "master_direction": "BULLISH",
        "master_conviction": "Alta",
        "master_confidence": "Alta",
        "master_status": audit_status,
        "master_risk": "Baixo",
        "master_summary": "Fluxo comprador, smart money positivo e liquidez adequada.",
        "master_reasoning": {"flow_reason": "Fluxo comprador", "macro_reason": "Macro neutro"},
        "master_consensus": {"aligned_count": 7, "opposing_count": 1, "ratio": 0.78, "total": 9},
        "strategic_panel": {"recommended_action": "OPORTUNIDADE CONFIRMADA", "no_trade_now": False},
        "strategic_panel_summary": "Fluxo comprador e Auditor aprovado. Risco baixo.",
        "radar_prioritization_score": 90.0,
        "radar_level": "🔥 PRIORIDADE ALTA",
        "radar_no_trade_now": False,
        "ranking_opportunity_score": 91.0,
        "ranking_classification": "🥇 Excelente",
        "ranking_eligible": True,
        "historical_confidence_score": 82.0,
        "historical_confidence_label": "🟢 Alta Confiança Histórica",
        "historical_sample_size": 24,
        "historical_win_rate": 80.0,
        "operational_status": "READY",
        "operational_ready": True,
        "operational_score": 88.0,
        "operational_blocks": [],
        "operational_warnings": [],
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


def _ai_tools(ticker="PETR4", macro_comment="macro bullish", risk_score=22, risk_state="low_risk"):
    def tool(name, score, state, comment):
        return {"ticker": ticker, "tool": name, "score": score, "state": state, "ai_comment": comment, "metrics": {f"{name}_score": score}}

    return {
        "flow": [tool("flow", 88, "institutional_buying", "fluxo comprador bull")],
        "liquidity": [tool("liquidity", 80, "liquidity_zone", "liquidez adequada bull")],
        "trend": [tool("trend", 86, "uptrend_structure", "tendencia bull")],
        "momentum": [tool("momentum", 82, "momentum_expansion", "momentum comprador")],
        "smart_money": [tool("smart_money", 87, "institutional_accumulation", "smart money bullish")],
        "news": [tool("news", 64, "news_available", "noticia positiva bull")],
        "macro": [tool("macro", 58, "macro_context_available", macro_comment)],
        "regime": [tool("regime", 84, "bull_trend", "regime bull_trend")],
        "risk": [_risk_tool(ticker, risk_score, risk_state)["risk"][0]],
    }


def _history(ticker="PETR4", wins=9, losses=1):
    return [{**_row(ticker), "historical_result": "win" if index < wins else "loss"} for index in range(wins + losses)]


class InstitutionalConvictionTests(unittest.TestCase):
    def test_conviction_levels(self):
        very_high, _ = enrich_institutional_conviction_rows([_row("VH1")], ai_tools=_ai_tools("VH1"), market_pulse={"sentiment": "bullish"})
        high, _ = enrich_institutional_conviction_rows(
            [
                _row(
                    "HIGH1",
                    master_consensus={},
                    master_confidence="Média",
                    historical_confidence_score=58.0,
                    historical_confidence_label="🟡 Confiança Histórica Moderada",
                    ranking_classification="🥈 Forte",
                )
            ],
            ai_tools=_risk_tool("HIGH1", score=35, state="low_risk"),
            market_pulse={"sentiment": "bullish"},
        )
        moderate, _ = enrich_institutional_conviction_rows(
            [
                _row(
                    "MOD1",
                    master_consensus={},
                    radar_level="⚪ OBSERVAÇÃO",
                    ranking_classification="⚪ Observação",
                    historical_confidence_score=0.0,
                    historical_confidence_label="⚪ Amostra Insuficiente",
                    historical_sample_size=2,
                )
            ],
            ai_tools=_risk_tool("MOD1"),
            market_pulse={"sentiment": "bullish"},
        )
        low, _ = enrich_institutional_conviction_rows(
            [
                _row(
                    "LOW1",
                    audit_status=AUDIT_CAUTION,
                    master_status=AUDIT_CAUTION,
                    master_confidence="Baixa",
                    master_consensus={"aligned_count": 2, "opposing_count": 5, "ratio": 0.22, "total": 9},
                    historical_confidence_score=30.0,
                    historical_confidence_label="🔴 Baixa Confiança Histórica",
                    master_risk="Alto",
                    operational_status="CAUTION",
                    operational_ready=False,
                )
            ],
            ai_tools=_risk_tool("LOW1", score=76, state="high_risk"),
            market_pulse={"sentiment": "neutral"},
        )

        self.assertEqual(very_high[0]["conviction_level"], CONVICTION_VERY_HIGH)
        self.assertEqual(high[0]["conviction_level"], CONVICTION_HIGH)
        self.assertEqual(moderate[0]["conviction_level"], CONVICTION_MODERATE)
        self.assertEqual(low[0]["conviction_level"], CONVICTION_LOW)

    def test_consensus_history_risk_and_conflicts_change_conviction(self):
        aligned, _ = enrich_institutional_conviction_rows([_row("ALIN1")], ai_tools=_ai_tools("ALIN1"), market_pulse={"sentiment": "bullish"})
        conflicted, _ = enrich_institutional_conviction_rows(
            [
                _row(
                    "CONF1",
                    master_consensus={"aligned_count": 3, "opposing_count": 4, "ratio": 0.33, "total": 9},
                    historical_confidence_score=35.0,
                    historical_confidence_label="🔴 Baixa Confiança Histórica",
                    master_risk="Alto",
                )
            ],
            ai_tools=_ai_tools("CONF1", macro_comment="macro bearish", risk_score=78, risk_state="high_risk"),
            market_pulse={"sentiment": "neutral"},
        )

        self.assertGreater(aligned[0]["conviction_score"], conflicted[0]["conviction_score"])
        self.assertIn("consenso institucional baixo", conflicted[0]["conviction_conflicts"])
        self.assertIn("histórico fraco", conflicted[0]["conviction_conflicts"])
        self.assertIn("risco elevado", conflicted[0]["conviction_conflicts"])
        self.assertTrue(any("Macro bearish" == item for item in conflicted[0]["conviction_conflicts"]))
        self.assertIn("conviction_summary", aligned[0])

    def test_operational_block_does_not_prevent_informative_conviction(self):
        rows, _ = enrich_institutional_conviction_rows(
            [
                _row(
                    "BLOQ1",
                    operational_status="BLOCKED",
                    operational_ready=False,
                    operational_blocks=["data quality stale"],
                )
            ],
            ai_tools=_ai_tools("BLOQ1"),
            market_pulse={"sentiment": "bullish"},
        )

        self.assertGreater(rows[0]["conviction_score"], 0)
        self.assertIn("operação bloqueada pelas regras operacionais", rows[0]["conviction_conflicts"])

    def test_snapshot_propagates_conviction_to_contracts(self):
        with patch("app.engine.market_snapshot_engine.build_ai_payload_bundle", return_value={"ai_tools": _ai_tools(), "internal_engine_keys": []}), patch(
            "app.ai.historical_confidence.get_history",
            return_value=_history("PETR4"),
        ):
            payload = build_snapshot_payload([_row("PETR4")], source="test")

        signal = payload["signals"][0]
        self.assertIn("institutional_convictions", payload)
        self.assertIn("conviction_metrics", payload)
        self.assertIn("conviction_score", signal)
        self.assertIn("conviction_score", payload["master_score"])
        self.assertIn("conviction_score", payload["strategic_panel"])

    def test_workspace_ranking_and_public_api_consume_conviction(self):
        enriched, _ = enrich_institutional_conviction_rows(
            [_row("PETR4"), _row("VALE3", master_score=72.0, ranking_opportunity_score=70.0, radar_prioritization_score=68.0)],
            ai_tools=_ai_tools("PETR4"),
            market_pulse={"sentiment": "bullish"},
        )
        snapshot = {
            "signals": enriched,
            "ai_tools": workspace_service._empty_ai_outputs(),
            "market_pulse": {"sentiment": "bullish"},
            "institutional_convictions": enriched,
            "conviction_metrics": {"signals": 2, "average_conviction": 80.0},
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

        self.assertIn("conviction_score", ranked[0])
        self.assertEqual(payload["institutional_convictions"][0]["ticker"], "PETR4")
        self.assertEqual(payload["market_snapshot"]["conviction_metrics"]["signals"], 2)
        self.assertEqual(insight["conviction_level"], enriched[0]["conviction_level"])

    def test_metrics_record_average_high_low_and_conflicts(self):
        enrich_institutional_conviction_rows(
            [
                _row("HIGHM"),
                _row(
                    "LOWM",
                    master_confidence="Baixa",
                    master_consensus={"aligned_count": 2, "opposing_count": 5, "ratio": 0.22, "total": 9},
                    historical_confidence_label="🔴 Baixa Confiança Histórica",
                    historical_confidence_score=30,
                    master_risk="Alto",
                ),
            ],
            ai_tools=_ai_tools("HIGHM"),
            market_pulse={"sentiment": "neutral"},
            record_metrics=True,
        )

        metrics = get_performance_metrics_snapshot()["institutional_conviction"]
        self.assertEqual(metrics["signals"], 2)
        self.assertGreater(metrics["average_conviction"], 0)
        self.assertGreaterEqual(metrics["high_conviction"], 1)
        self.assertGreaterEqual(metrics["low_conviction"], 1)
        self.assertGreater(metrics["conflicts_detected"], 0)


if __name__ == "__main__":
    unittest.main()
