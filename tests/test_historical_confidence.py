import unittest
from unittest.mock import patch

from app.ai.historical_confidence import (
    HISTORICAL_HIGH,
    HISTORICAL_INSUFFICIENT,
    HISTORICAL_LOW,
    HISTORICAL_MODERATE,
    enrich_historical_confidence_rows,
    historical_confidence_items,
)
from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED, AUDIT_CAUTION
from app.ai.institutional_radar import institutional_radar_items
from app.ai.institutional_ranking import institutional_ranking_items
from app.api import routes_public_market_live
from app.engine.market_snapshot_engine import build_snapshot_payload
from app.services import ranking, workspace_service
from app.system.system_metrics import get_performance_metrics_snapshot


def _row(ticker="PETR4", audit_status=AUDIT_APPROVED, **overrides):
    row = {
        "ticker": ticker,
        "symbol": ticker,
        "score": 90.0,
        "signal": "BUY",
        "trade_action": "BUY",
        "decision_ready": True,
        "decision_state": "BUY_READY",
        "can_trade": True,
        "data_quality": "cached",
        "price": 38.0,
        "volume": 1_500_000,
        "audit_status": audit_status,
        "auditor_status": audit_status,
        "audit_score": 92.0 if audit_status == AUDIT_APPROVED else 68.0 if audit_status == AUDIT_CAUTION else 20.0,
        "audit_confidence": "Alta",
        "audit_blocks": ["baixa liquidez"] if audit_status == AUDIT_BLOCKED else [],
        "audit_warnings": ["atenção"] if audit_status == AUDIT_CAUTION else [],
        "blocked_by_auditor": audit_status == AUDIT_BLOCKED,
        "master_score": 86.0,
        "master_direction": "BULLISH",
        "master_conviction": "Alta",
        "master_confidence": "Alta",
        "master_status": audit_status,
        "master_risk": "Baixo",
        "master_summary": "Fluxo comprador e smart money positivo.",
        "master_reasoning": {"flow_reason": "Fluxo comprador", "regime_reason": "bull_trend"},
        "master_consensus": {"aligned_count": 7, "opposing_count": 1, "ratio": 0.78, "total": 9},
        "strategic_panel": {
            "recommended_action": "OPORTUNIDADE CONFIRMADA",
            "strategic_panel_summary": "Fluxo comprador e Auditor aprovado. Risco baixo.",
            "no_trade_now": False,
            "risk_block": {"level": "Baixo", "score": 20},
        },
        "strategic_panel_summary": "Fluxo comprador e Auditor aprovado. Risco baixo.",
        "recommended_action": "OPORTUNIDADE CONFIRMADA",
        "radar_prioritization_score": 88.0,
        "radar_level": "🔥 PRIORIDADE ALTA",
        "radar_no_trade_now": False,
        "ranking_opportunity_score": 90.0,
        "ranking_classification": "🥇 Excelente",
        "ranking_eligible": True,
        "market_regime_state": "bull_trend",
        "generated_at": "2026-06-12T13:30:00+00:00",
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


def _history(ticker="PETR4", wins=8, losses=2, **overrides):
    rows = []
    for index in range(wins + losses):
        outcome = "win" if index < wins else "loss"
        rows.append(_row(ticker, historical_result=outcome, **overrides))
    return rows


def _bearish_row(ticker="VALE3", **overrides):
    return _row(
        ticker,
        signal="SHORT",
        trade_action="SHORT",
        decision_state="SHORT_READY",
        master_direction="BEARISH",
        master_summary="Fluxo vendedor e regime de baixa.",
        master_reasoning={"flow_reason": "Fluxo vendedor", "regime_reason": "bear_trend"},
        market_regime_state="bear_trend",
        radar_level="🔥 PRIORIDADE ALTA",
        ranking_classification="🥇 Excelente",
        **overrides,
    )


def _risk_tool(ticker="PETR4", score=20, state="low_risk"):
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


class HistoricalConfidenceTests(unittest.TestCase):
    def test_high_moderate_low_and_insufficient_labels(self):
        high, _ = enrich_historical_confidence_rows([_row("ALTA1")], history_rows=_history("ALTA1", wins=9, losses=1))
        moderate, _ = enrich_historical_confidence_rows([_row("MOD1")], history_rows=_history("MOD1", wins=7, losses=5))
        low, _ = enrich_historical_confidence_rows([_row("LOW1")], history_rows=_history("LOW1", wins=2, losses=8))
        insufficient, _ = enrich_historical_confidence_rows([_row("INS1")], history_rows=_history("INS1", wins=3, losses=0))

        self.assertEqual(high[0]["historical_confidence_label"], HISTORICAL_HIGH)
        self.assertEqual(moderate[0]["historical_confidence_label"], HISTORICAL_MODERATE)
        self.assertEqual(low[0]["historical_confidence_label"], HISTORICAL_LOW)
        self.assertEqual(insufficient[0]["historical_confidence_label"], HISTORICAL_INSUFFICIENT)
        self.assertIn("Amostra insuficiente", insufficient[0]["historical_warning"])

    def test_ticker_without_history_and_high_score_without_sample_are_insufficient(self):
        rows, _ = enrich_historical_confidence_rows(
            [_row("SEM1", master_score=99.0)],
            history_rows=_history("OUTRO", wins=10, losses=0),
        )

        self.assertEqual(rows[0]["historical_sample_size"], 0)
        self.assertEqual(rows[0]["historical_confidence_label"], HISTORICAL_INSUFFICIENT)
        self.assertEqual(rows[0]["historical_confidence_score"], 0.0)

    def test_bullish_and_bearish_history_use_matching_direction(self):
        bullish, _ = enrich_historical_confidence_rows([_row("PETR4")], history_rows=_history("PETR4", wins=8, losses=2))
        bearish_history = [_bearish_row("VALE3", historical_result="win") for _ in range(9)] + [_bearish_row("VALE3", historical_result="loss")]
        bearish, _ = enrich_historical_confidence_rows([_bearish_row("VALE3")], history_rows=bearish_history)
        wrong_direction, _ = enrich_historical_confidence_rows([_bearish_row("PETR4")], history_rows=_history("PETR4", wins=10, losses=0))

        self.assertGreaterEqual(bullish[0]["historical_win_rate"], 80)
        self.assertGreaterEqual(bearish[0]["historical_win_rate"], 80)
        self.assertEqual(wrong_direction[0]["historical_sample_size"], 0)

    def test_auditor_blocked_does_not_turn_history_into_permission(self):
        rows, _ = enrich_historical_confidence_rows(
            [_row("BLOQ1", audit_status=AUDIT_BLOCKED, master_status=AUDIT_BLOCKED)],
            history_rows=_history("BLOQ1", wins=9, losses=1, audit_status=AUDIT_BLOCKED, master_status=AUDIT_BLOCKED),
        )

        self.assertEqual(rows[0]["historical_confidence_label"], HISTORICAL_HIGH)
        self.assertIn("não libera operação", rows[0]["historical_warning"])
        self.assertEqual(rows[0]["master_score"], 86.0)
        self.assertEqual(rows[0]["master_confidence"], "Alta")

    def test_snapshot_propagates_historical_confidence_to_contracts(self):
        with patch("app.engine.market_snapshot_engine.build_ai_payload_bundle", return_value={"ai_tools": _bullish_tools(), "internal_engine_keys": []}), patch(
            "app.ai.historical_confidence.get_history",
            return_value=_history("PETR4", wins=9, losses=1),
        ):
            payload = build_snapshot_payload([_row("PETR4")], source="test")

        signal = payload["signals"][0]
        self.assertIn("historical_confidences", payload)
        self.assertIn("historical_confidence_metrics", payload)
        self.assertIn("historical_confidence_score", signal)
        self.assertIn("historical_confidence_score", payload["master_score"])
        self.assertIn("historical_confidence_score", payload["strategic_panel"])
        self.assertGreaterEqual(payload["historical_confidence_metrics"]["average_confidence_score"], 1)

    def test_workspace_ranking_radar_and_public_api_consume_contract(self):
        enriched, _ = enrich_historical_confidence_rows(
            [_row("PETR4"), _row("VALE3", master_score=68.0, ranking_opportunity_score=70.0, radar_prioritization_score=66.0)],
            history_rows=_history("PETR4", wins=9, losses=1) + _history("VALE3", wins=7, losses=3),
        )
        snapshot = {
            "signals": enriched,
            "ai_tools": workspace_service._empty_ai_outputs(),
            "market_pulse": {"sentiment": "bullish"},
            "institutional_ranking": institutional_ranking_items(enriched, limit=20),
            "institutional_radar": institutional_radar_items(enriched, limit=20),
            "historical_confidences": historical_confidence_items(enriched, limit=20),
            "historical_confidence": enriched[0],
            "historical_confidence_metrics": {"signals": 2, "average_confidence_score": 80.0},
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

        self.assertIn("historical_confidence_score", ranked[0])
        self.assertIn("historical_confidence_score", institutional_radar_items(enriched, limit=20)[0])
        self.assertIn("historical_confidence", payload)
        self.assertEqual(payload["ranking"][0]["ticker"], "PETR4")
        self.assertEqual(insight["historical_confidence_label"], enriched[0]["historical_confidence_label"])

    def test_metrics_record_average_sample_without_sample_and_win_rate(self):
        enrich_historical_confidence_rows(
            [_row("PETR4"), _row("SEM1")],
            history_rows=_history("PETR4", wins=8, losses=2),
            record_metrics=True,
        )

        metrics = get_performance_metrics_snapshot()["historical_confidence"]
        self.assertEqual(metrics["signals"], 2)
        self.assertEqual(metrics["signals_without_sample"], 1)
        self.assertGreater(metrics["average_sample_size"], 0)
        self.assertGreater(metrics["aggregate_win_rate"], 0)
        self.assertIn("PETR4", metrics["by_ticker"])


if __name__ == "__main__":
    unittest.main()
