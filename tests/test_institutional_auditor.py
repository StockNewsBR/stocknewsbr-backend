import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED, AUDIT_CAUTION, build_institutional_audit
from app.engine import market_snapshot_engine
from app.engine.market_snapshot_engine import build_snapshot_payload
from app.services import ranking
from app.api import market_routes
from app.system import push_dispatcher
from app.telegram import telegram_alert_engine
from app.services import workspace_service


def _row(**overrides):
    base = {
        "ticker": "PETR4",
        "symbol": "PETR4",
        "score": 88.0,
        "signal": "BUY",
        "trade_action": "BUY",
        "decision_ready": True,
        "decision_state": "BUY_READY",
        "data_quality": "priced",
        "price": 37.5,
        "volume": 1_200_000,
        "avg_volume": 800_000,
        "rel_volume": 1.5,
        "vwap": 37.1,
        "rsi": 58.0,
        "adx": 24.0,
        "atr_pct": 1.8,
        "momentum": 1.2,
        "change_pct": 1.4,
        "above_vwap": True,
        "trend_strength": 66.0,
    }
    base.update(overrides)
    return base


def _ai_tools(**overrides):
    tools = {
        "trend": [{"ticker": "PETR4", "tool": "trend", "score": 82, "state": "uptrend_structure"}],
        "momentum": [{"ticker": "PETR4", "tool": "momentum", "score": 74, "state": "momentum_expansion"}],
        "smart_money": [{"ticker": "PETR4", "tool": "smart_money", "score": 81, "state": "institutional_accumulation"}],
        "liquidity": [{"ticker": "PETR4", "tool": "liquidity", "score": 68, "state": "liquidity_zone"}],
        "regime": [{"ticker": "PETR4", "tool": "regime", "score": 80, "state": "bull_trend", "metrics": {"regime_state": "bull_trend"}}],
        "risk": [{"ticker": "PETR4", "tool": "risk", "score": 25, "state": "low_risk", "metrics": {"risk_score": 25, "risk_blocks": []}}],
        "news": [{"ticker": "PETR4", "tool": "news", "score": 52, "state": "news_available", "ai_comment": "noticia positiva bull"}],
        "macro": [{"ticker": "PETR4", "tool": "macro", "score": 55, "state": "macro_context_available"}],
    }
    tools.update(overrides)
    return tools


class InstitutionalAuditorTests(unittest.TestCase):
    def test_auditor_approves_clean_institutional_context(self):
        audit = build_institutional_audit(
            _row(),
            ai_tools=_ai_tools(),
            market_pulse={"sentiment": "bullish", "bullish_ratio": 0.7, "bearish_ratio": 0.3},
        )

        self.assertEqual(audit["audit_status"], AUDIT_APPROVED)
        self.assertTrue(audit["auditor_approved"])
        self.assertFalse(audit["blocked_by_auditor"])
        self.assertGreaterEqual(audit["audit_score"], 80)

    def test_auditor_blocks_bad_data_snapshot_and_zero_market_fields(self):
        audit = build_institutional_audit(
            _row(data_quality="score_only", price=0, volume=0),
            ai_tools=_ai_tools(),
            snapshot_context={"stale": True, "source": "snapshot_fallback"},
        )

        self.assertEqual(audit["audit_status"], AUDIT_BLOCKED)
        self.assertTrue(audit["blocked_by_auditor"])
        self.assertIn("Data Quality Ruim", audit["audit_blocks"])
        self.assertIn("Preco Ausente", audit["audit_blocks"])
        self.assertIn("Volume Ausente", audit["audit_blocks"])
        self.assertIn("Snapshot Invalido", audit["audit_blocks"])

    def test_auditor_blocks_provider_error_no_trade_and_radar_invalid(self):
        audit = build_institutional_audit(
            _row(
                action="DO_NOT_TRADE",
                data_quality="score_only",
                provider_error=True,
                radar_state="invalid",
            ),
            ai_tools=_ai_tools(
                momentum=[{"ticker": "PETR4", "tool": "momentum", "score": 78, "state": "radar_invalid"}],
                risk=[{"ticker": "PETR4", "tool": "risk", "score": 82, "state": "high_risk", "metrics": {"risk_score": 82}}],
            ),
        )

        self.assertEqual(audit["audit_status"], AUDIT_BLOCKED)
        self.assertIn("Provider Error", audit["audit_blocks"])
        self.assertIn("NO_TRADE", audit["audit_blocks"])
        self.assertIn("Radar Invalido", audit["audit_blocks"])
        self.assertIn("Risk IA Bloqueando", audit["audit_blocks"])

    def test_auditor_blocks_conflicting_trend_smart_money_and_liquidity(self):
        audit = build_institutional_audit(
            _row(),
            ai_tools=_ai_tools(
                trend=[{"ticker": "PETR4", "tool": "trend", "score": 84, "state": "uptrend_structure"}],
                smart_money=[{"ticker": "PETR4", "tool": "smart_money", "score": 22, "state": "institutional_distribution"}],
                liquidity=[{"ticker": "PETR4", "tool": "liquidity", "score": 72, "state": "thin_liquidity"}],
            ),
        )

        self.assertEqual(audit["audit_status"], AUDIT_BLOCKED)
        self.assertTrue(audit["conflict_detected"])
        self.assertIn("Conflito de Tendencia", audit["audit_blocks"])

    def test_auditor_returns_caution_for_news_macro_regime_divergence(self):
        audit = build_institutional_audit(
            _row(),
            ai_tools=_ai_tools(
                news=[{"ticker": "PETR4", "tool": "news", "score": 78, "state": "news_available", "ai_comment": "bull positive"}],
                macro=[{"ticker": "PETR4", "tool": "macro", "score": 30, "state": "macro_context_available", "ai_comment": "bear macro"}],
                regime=[{"ticker": "PETR4", "tool": "regime", "score": 45, "state": "range", "metrics": {"regime_state": "range"}}],
            ),
        )

        self.assertEqual(audit["audit_status"], AUDIT_CAUTION)
        self.assertTrue(audit["conflict_detected"])
        self.assertIn("News positiva com macro/regime desfavoravel", audit["audit_warnings"])

    def test_auditor_blocks_market_pulse_inconsistency_and_risk_ia(self):
        pulse_audit = build_institutional_audit(
            _row(signal="BUY", trade_action="BUY"),
            ai_tools=_ai_tools(),
            market_pulse={"sentiment": "bearish", "bearish_ratio": 0.7, "bullish_ratio": 0.3},
        )
        risk_audit = build_institutional_audit(
            _row(),
            ai_tools=_ai_tools(risk=[{"ticker": "PETR4", "tool": "risk", "score": 82, "state": "high_risk", "metrics": {"risk_score": 82}}]),
        )

        self.assertEqual(pulse_audit["audit_status"], AUDIT_BLOCKED)
        self.assertIn("Market Pulse Inconsistente", pulse_audit["audit_blocks"])
        self.assertEqual(risk_audit["audit_status"], AUDIT_BLOCKED)
        self.assertIn("Risk IA Bloqueando", risk_audit["audit_blocks"])

    def test_snapshot_carries_auditor_contract(self):
        with patch.object(market_snapshot_engine, "get_market_pool", return_value={}):
            payload = build_snapshot_payload([_row(data_quality="score_only", price=0, volume=0)])

        signal = payload["signals"][0]
        self.assertIn("auditor", payload)
        self.assertEqual(signal["audit_status"], AUDIT_BLOCKED)
        self.assertTrue(signal["blocked_by_auditor"])
        self.assertIn("auditor_blocked", signal["blocked_reasons"])

    def test_ranking_radar_telegram_and_push_block_auditor_rejected_rows(self):
        blocked = {
            **_row(score=99.0),
            "audit_status": AUDIT_BLOCKED,
            "blocked_by_auditor": True,
            "auditor": {"audit_status": AUDIT_BLOCKED, "blocked_by_auditor": True},
        }
        allowed = _row(ticker="VALE3", symbol="VALE3", score=91.0)

        with patch.object(ranking, "get_snapshot_info", return_value={"signals": 2, "age_seconds": 0, "timestamp": 1, "has_signals": True, "is_empty": False}), patch.object(
            ranking,
            "get_snapshot_signals",
            return_value=[blocked, allowed],
        ):
            ranked = ranking.get_ranking(force_refresh=True)

        with patch.object(market_routes, "get_snapshot_signals", return_value=[{**blocked, "events": ["momentum"]}, {**allowed, "events": ["momentum"]}]):
            radar = market_routes.get_market_radar(current_user=SimpleNamespace(plan="premium"))

        with patch.object(telegram_alert_engine, "format_signal_alert") as format_alert, patch.object(telegram_alert_engine, "send_alert") as send_alert:
            telegram_alert_engine.send_signal_alert(blocked)

        self.assertEqual([row["ticker"] for row in ranked], ["VALE3"])
        self.assertEqual([row["ticker"] for row in radar["momentum"]], ["VALE3"])
        self.assertEqual(push_dispatcher._eligible_signals([blocked]), [])
        format_alert.assert_not_called()
        send_alert.assert_not_called()

    def test_workspace_exposes_auditor_and_does_not_promote_blocked_rows(self):
        blocked = {
            **_row(score=99.0),
            "audit_status": AUDIT_BLOCKED,
            "blocked_by_auditor": True,
            "auditor": {"audit_status": AUDIT_BLOCKED, "blocked_by_auditor": True},
        }
        allowed = _row(ticker="VALE3", symbol="VALE3", score=91.0)
        snapshot = {
            "signals": [blocked, allowed],
            "ai_tools": workspace_service._empty_ai_outputs(),
            "auditor": {"status": AUDIT_BLOCKED, "blocked": 1},
            "market_pulse": {"sentiment": "neutral"},
        }
        bootstrap = {
            "brand": "StockNewsBR",
            "pricing": {"trial_days": 30},
            "launch_roadmap": {"current": "web"},
            "ai_modules": [],
            "social_features": {},
        }
        metrics = {
            "engine_cycles": 1,
            "signals_generated": 2,
            "assets_scanned": 2,
            "cache_age": 0,
            "http_requests": 0,
            "ws_connections": 0,
            "chat_messages": 0,
        }
        with patch.object(workspace_service, "get_public_bootstrap", return_value=bootstrap), patch.object(
            workspace_service,
            "get_metrics_snapshot",
            return_value=metrics,
        ), patch.object(workspace_service, "get_snapshot", return_value=snapshot), patch.object(
            workspace_service,
            "get_ranking",
            return_value=[],
        ), patch.object(workspace_service, "get_posts", return_value=[]), patch.object(
            workspace_service,
            "get_help_center_blueprint",
            return_value={"guides": []},
        ), patch.object(workspace_service, "get_media_status", return_value={}), patch.object(
            workspace_service,
            "get_push_status",
            return_value={},
        ), patch.object(workspace_service, "get_user_workspace_layout", return_value={"tabs": ["home"], "pinned_ticker": "PETR4", "opened_popouts": []}), patch.object(
            workspace_service,
            "get_layout",
            return_value={"tabs": [{"id": "home", "title": "Home"}]},
        ), patch.object(workspace_service, "list_room_messages", return_value=[]), patch.object(
            workspace_service,
            "persist_ai_alert_history",
            side_effect=lambda value: value,
        ):
            payload = workspace_service.get_workspace_data(user_id=7, channel="web")

        self.assertEqual([row["ticker"] for row in payload["ranking"]], ["VALE3"])
        self.assertEqual(payload["blocked_signals"][0]["ticker"], "PETR4")
        self.assertEqual(payload["auditor"]["status"], AUDIT_BLOCKED)


if __name__ == "__main__":
    unittest.main()
