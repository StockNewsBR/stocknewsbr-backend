import unittest
from unittest.mock import patch

from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED, AUDIT_CAUTION
from app.ai.institutional_ranking import (
    RANKING_EXCELLENT,
    RANKING_MODERATE,
    RANKING_NO_TRADE,
    RANKING_STRONG,
    RANKING_WATCH,
    enrich_institutional_ranking_rows,
    institutional_ranking_items,
)
from app.api import routes_public_market_live
from app.engine.market_snapshot_engine import build_snapshot_payload
from app.services import ranking, workspace_service
from app.system.system_metrics import get_performance_metrics_snapshot


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
        "radar_prioritization_score": 90.0,
        "radar_level": "🔥 PRIORIDADE ALTA",
        "radar_reason": "Fluxo comprador, Smart Money positivo e Auditor aprovado.",
        "radar_summary": "Radar em prioridade alta.",
        "radar_no_trade_now": False,
        "radar_blocked_reasons": [],
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
    row.setdefault("ranking_eligible", row.get("decision_ready") is True)
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


class InstitutionalRankingTests(unittest.TestCase):
    def test_classification_excellent_strong_moderate_and_watch(self):
        excellent = _row("EXC1")
        strong = _row("FOR1", master_score=65.0, radar_prioritization_score=60.0, audit_score=75.0, master_conviction="Média")
        moderate = _row("MOD1", master_score=50.0, radar_prioritization_score=40.0, audit_score=70.0, master_conviction="Média", master_confidence="Média")
        watch = _row("OBS1", master_score=35.0, radar_prioritization_score=30.0, audit_score=60.0, master_conviction="Baixa", master_confidence="Média")

        rows, _ = enrich_institutional_ranking_rows(
            [excellent, strong, moderate, watch],
            ai_tools=_risk_tool(score=45, state="medium_risk"),
            market_pulse={"sentiment": "bullish"},
        )

        by_ticker = {row["ticker"]: row for row in rows}
        self.assertEqual(by_ticker["EXC1"]["ranking_classification"], RANKING_EXCELLENT)
        self.assertEqual(by_ticker["FOR1"]["ranking_classification"], RANKING_STRONG)
        self.assertEqual(by_ticker["MOD1"]["ranking_classification"], RANKING_MODERATE)
        self.assertEqual(by_ticker["OBS1"]["ranking_classification"], RANKING_WATCH)

    def test_auditor_blocked_radar_blocked_score_only_stale_and_bad_quality_are_excluded(self):
        rows, metrics = enrich_institutional_ranking_rows(
            [
                _row("BLOQ1", audit_status=AUDIT_BLOCKED),
                _row("RADR1", radar_no_trade_now=True, radar_blocked_reasons=["radar bloqueou"]),
                _row("SCOR1", data_quality="score_only", price=0, volume=0),
                _row("STAL1", data_quality="stale", is_stale=True),
                _row("INVA1", data_quality="invalid"),
            ],
            ai_tools=_risk_tool(),
        )

        self.assertEqual(metrics["excluded"], 5)
        self.assertTrue(all(row["ranking_classification"] == RANKING_NO_TRADE for row in rows))
        self.assertTrue(all(row["ranking_eligible"] is False for row in rows))

    def test_auditor_caution_and_risk_high_reduce_score_without_blocking(self):
        approved, _ = enrich_institutional_ranking_rows([_row("APRV1")], ai_tools=_risk_tool(score=22, state="low_risk"))
        caution, _ = enrich_institutional_ranking_rows([_row("CAUT1", audit_status=AUDIT_CAUTION, master_status=AUDIT_CAUTION)], ai_tools=_risk_tool(score=22, state="low_risk"))
        high_risk, _ = enrich_institutional_ranking_rows([_row("RISK1", master_risk="Alto")], ai_tools=_risk_tool(score=78, state="high_risk"))

        self.assertGreater(approved[0]["ranking_opportunity_score"], caution[0]["ranking_opportunity_score"])
        self.assertGreater(approved[0]["ranking_opportunity_score"], high_risk[0]["ranking_opportunity_score"])
        self.assertTrue(caution[0]["ranking_eligible"])
        self.assertTrue(high_risk[0]["ranking_eligible"])

    def test_critical_risk_blocks_ranking(self):
        rows, _ = enrich_institutional_ranking_rows([_row("CRIT1", master_risk="Crítico")], ai_tools=_risk_tool(score=90, state="critical_risk"))

        self.assertFalse(rows[0]["ranking_eligible"])
        self.assertIn("risco critico", rows[0]["ranking_excluded_reasons"])

    def test_consensus_and_confidence_change_ranking_score(self):
        strong = _row("CONS1", master_consensus={"aligned_count": 7, "opposing_count": 1, "ratio": 0.78, "total": 9}, master_confidence="Alta")
        weak = _row("CONS2", master_consensus={"aligned_count": 3, "opposing_count": 4, "ratio": 0.33, "total": 9}, master_confidence="Baixa", master_conviction="Baixa")

        rows, _ = enrich_institutional_ranking_rows([strong, weak], ai_tools=_risk_tool())
        by_ticker = {row["ticker"]: row for row in rows}

        self.assertGreater(by_ticker["CONS1"]["ranking_opportunity_score"], by_ticker["CONS2"]["ranking_opportunity_score"])
        self.assertIn("ranking_reason", by_ticker["CONS1"])
        self.assertLessEqual(len(by_ticker["CONS1"]["ranking_summary"]), 220)

    def test_institutional_ranking_items_only_returns_eligible_sorted_rows(self):
        rows, _ = enrich_institutional_ranking_rows(
            [_row("LOW1", master_score=60.0, radar_prioritization_score=50.0, master_conviction="Baixa"), _row("TOP1"), _row("BLOQ1", audit_status=AUDIT_BLOCKED)],
            ai_tools=_risk_tool(),
        )

        ranked = institutional_ranking_items(rows, limit=10)

        self.assertEqual(ranked[0]["ticker"], "TOP1")
        self.assertNotIn("BLOQ1", [row["ticker"] for row in ranked])

    def test_snapshot_propagates_ranking_contract_and_metrics(self):
        with patch("app.engine.market_snapshot_engine.build_ai_payload_bundle", return_value={"ai_tools": _bullish_tools(), "internal_engine_keys": []}):
            payload = build_snapshot_payload([_row()], source="test")

        signal = payload["signals"][0]
        self.assertIn("institutional_ranking", payload)
        self.assertIn("ranking_metrics", payload)
        self.assertIn("ranking_opportunity_score", signal)
        self.assertIn("ranking_reason", signal)
        self.assertIn("ranking_summary", signal)
        self.assertGreaterEqual(payload["ranking_metrics"]["eligible"], 1)

    def test_ranking_service_and_workspace_consume_contract(self):
        enriched, _ = enrich_institutional_ranking_rows(
            [_row("PETR4"), _row("VALE3", master_score=62.0, radar_prioritization_score=52.0, master_conviction="Baixa")],
            ai_tools=_risk_tool(),
        )
        snapshot = {
            "signals": enriched,
            "ai_tools": workspace_service._empty_ai_outputs(),
            "institutional_ranking": enriched,
            "ranking_metrics": {"eligible": 2, "promoted": 1},
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

        self.assertEqual(ranked[0]["ticker"], "PETR4")
        self.assertIn("ranking_opportunity_score", ranked[0])
        self.assertEqual(payload["ranking"][0]["ticker"], "PETR4")
        self.assertEqual(payload["market_snapshot"]["ranking_metrics"]["eligible"], 2)

    def test_public_api_exposes_ranking_fields(self):
        enriched, _ = enrich_institutional_ranking_rows([_row()], ai_tools=_risk_tool())

        with patch.object(routes_public_market_live, "get_snapshot_ticker", return_value=enriched[0]), patch.object(
            routes_public_market_live, "_load_chart_data_fast", return_value=[]
        ):
            insight = routes_public_market_live.public_market_insight("PETR4")

        self.assertEqual(insight["ranking_classification"], enriched[0]["ranking_classification"])
        self.assertEqual(insight["ranking_summary"], enriched[0]["ranking_summary"])

    def test_metrics_record_eligible_excluded_promoted_and_top_ranking(self):
        enrich_institutional_ranking_rows(
            [_row("PETR4"), _row("BLOQ1", audit_status=AUDIT_BLOCKED), _row("OBS1", master_score=60.0, radar_prioritization_score=50.0, master_conviction="Baixa")],
            ai_tools=_risk_tool(),
            record_metrics=True,
        )

        metrics = get_performance_metrics_snapshot()["institutional_ranking"]
        self.assertEqual(metrics["eligible"], 2)
        self.assertEqual(metrics["excluded"], 1)
        self.assertGreaterEqual(metrics["promoted"], 1)
        self.assertIn("top_ranking", metrics)


if __name__ == "__main__":
    unittest.main()
