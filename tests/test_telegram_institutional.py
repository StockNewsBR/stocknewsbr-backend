import unittest
from unittest.mock import patch

from app.ai.final_decision import FINAL_CONFIRMED, FINAL_FORMING, FINAL_NO_TRADE
from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED
from app.ai.institutional_conviction import CONVICTION_HIGH, CONVICTION_MODERATE, CONVICTION_VERY_HIGH
from app.ai.institutional_priority import PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_MEDIUM
from app.ai.operational_rules import OPERATIONAL_BLOCKED, OPERATIONAL_READY
from app.services import workspace_service
from app.system.system_metrics import format_prometheus_metrics, get_performance_metrics_snapshot
from app.telegram.telegram_alert_engine import (
    ALERT_CRITICAL,
    ALERT_HIGH,
    ALERT_MEDIUM,
    build_telegram_alert,
    get_telegram_alert_history,
    reset_telegram_alert_state,
    send_signal_alert,
    telegram_alert_fingerprint,
)
from app.telegram.telegram_alert_formatter import format_signal_alert, telegram_summary


def _row(**overrides):
    base = {
        "ticker": "PETR4",
        "symbol": "PETR4",
        "trade_action": "BUY",
        "decision_ready": True,
        "decision_state": "BUY_READY",
        "price": 37.5,
        "volume": 1_000_000,
        "data_quality": "priced",
        "final_decision": FINAL_CONFIRMED,
        "final_decision_score": 92.0,
        "final_decision_confidence": "Alta",
        "final_decision_summary": "Fluxo comprador, Smart Money positivo e historico favoravel.",
        "priority_level": PRIORITY_CRITICAL,
        "conviction_level": CONVICTION_VERY_HIGH,
        "operational_status": OPERATIONAL_READY,
        "audit_status": AUDIT_APPROVED,
        "master_score": 88.0,
        "master_direction": "BULLISH",
        "historical_confidence_score": 72.0,
        # Mission 31F: alertas Telegram exigem acesso validado explicitamente.
        "telegram_access": {"linked": True, "allowed": True, "reason": None},
    }
    base.update(overrides)
    base.setdefault("score_source_scale", "0_100")
    if base.get("master_score_source_scale") == "0_10":
        display_value = float(base.get("master_score") or 0.0)
        base.setdefault("master_score_raw", display_value if display_value > 10.0 else display_value * 10.0)
    else:
        base.setdefault("master_score_raw", base.get("master_score"))
        base.setdefault("master_score_source_scale", "0_100")
    base.setdefault("ranking_opportunity_source_scale", "0_100")
    return base


class TelegramInstitutionalTests(unittest.TestCase):
    def setUp(self):
        reset_telegram_alert_state()

    def test_alerta_critico_consumes_final_contracts_and_formats_message(self):
        before = get_performance_metrics_snapshot()["telegram_alerts"]

        with patch("app.telegram.telegram_alert_engine.send_alert", return_value=True) as send_alert:
            result = send_signal_alert(_row(), now=1000, cooldown_seconds=1800)

        after = get_performance_metrics_snapshot()["telegram_alerts"]
        message = send_alert.call_args.args[0]

        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["alert_level"], ALERT_CRITICAL)
        self.assertIn("ALERTA CRÍTICO", message)
        self.assertIn("OPORTUNIDADE CONFIRMADA", message)
        self.assertIn("Score Mestre: 8.8", message)
        self.assertIn("Auditor: APROVADO", message)
        self.assertGreaterEqual(after["sent"], before["sent"] + 1)
        self.assertGreaterEqual(after["critical"], before["critical"] + 1)

    def test_alert_formatter_keeps_display_scale_rows_at_0_10(self):
        message = format_signal_alert(
            _row(
                master_score=8.7,
                score=8.7,
                master_score_source_scale="0_10",
                score_source_scale="0_10",
                ranking_opportunity_source_scale="0_10",
            )
        )

        self.assertIn("Score Mestre: 8.7", message)
        self.assertNotIn("Score Mestre: 87", message)

        raw_and_display_message = format_signal_alert(
            _row(
                master_score=8.7,
                score=8.7,
                master_score_raw=87.0,
                master_score_source_scale="0_10",
                score_source_scale="0_10",
                ranking_opportunity_source_scale="0_10",
            )
        )
        self.assertIn("Score Mestre: 8.7", raw_and_display_message)
        self.assertNotIn("Score Mestre: 87", raw_and_display_message)

    def test_alerta_alto_e_medio_are_classified_without_low_alert(self):
        high = build_telegram_alert(
            _row(
                ticker="VALE3",
                priority_level=PRIORITY_HIGH,
                conviction_level=CONVICTION_HIGH,
                final_decision_score=81.0,
            )
        )
        medium = build_telegram_alert(
            _row(
                ticker="ITUB4",
                final_decision=FINAL_FORMING,
                priority_level=PRIORITY_MEDIUM,
                conviction_level=CONVICTION_MODERATE,
                final_decision_score=66.0,
            )
        )
        low = build_telegram_alert(
            _row(
                ticker="BBDC4",
                final_decision=FINAL_FORMING,
                priority_level="⚪ BAIXA",
                conviction_level=CONVICTION_MODERATE,
                final_decision_score=41.0,
            )
        )

        self.assertEqual(high["alert_level"], ALERT_HIGH)
        self.assertEqual(medium["alert_level"], ALERT_MEDIUM)
        self.assertEqual(low["status"], "discarded")

    def test_bloqueios_institucionais_do_not_format_or_send(self):
        blocked_rows = [
            _row(ticker="AUDIT", audit_status=AUDIT_BLOCKED),
            _row(ticker="OPER", operational_status=OPERATIONAL_BLOCKED),
            _row(ticker="FINAL", final_decision=FINAL_NO_TRADE),
            _row(ticker="READY", decision_ready=False),
            _row(ticker="RADAR", radar_no_trade_now=True),
        ]

        with patch("app.telegram.telegram_alert_engine.format_signal_alert") as formatter, patch(
            "app.telegram.telegram_alert_engine.send_alert"
        ) as sender:
            results = [send_signal_alert(row) for row in blocked_rows]

        self.assertTrue(all(result["status"] == "blocked" for result in results))
        formatter.assert_not_called()
        sender.assert_not_called()

    def test_deduplicacao_usa_fingerprint_do_contexto_final(self):
        row = _row()
        first_fingerprint = telegram_alert_fingerprint(row)

        with patch("app.telegram.telegram_alert_engine.send_alert", return_value=True):
            first = send_signal_alert(row, now=1000, cooldown_seconds=1800)
            second = send_signal_alert(row, now=1005, cooldown_seconds=1800)

        self.assertEqual(first["status"], "sent")
        self.assertEqual(second["status"], "deduplicated")
        self.assertEqual(first_fingerprint, second["fingerprint"])

    def test_cooldown_blocks_equivalent_alert_with_changed_context(self):
        row = _row()
        changed_context = _row(final_decision_summary="Mesmo ativo, mesma direcao, contexto textual atualizado.")

        with patch("app.telegram.telegram_alert_engine.send_alert", return_value=True):
            first = send_signal_alert(row, now=1000, cooldown_seconds=1800)
            second = send_signal_alert(changed_context, now=1010, cooldown_seconds=1800)

        self.assertEqual(first["status"], "sent")
        self.assertEqual(second["status"], "cooldown")
        self.assertGreater(second["cooldown_remaining_seconds"], 0)

    def test_telegram_summary_keeps_three_lines_max(self):
        summary = telegram_summary(
            _row(
                final_decision_summary="linha 1\nlinha 2\nlinha 3\nlinha 4",
                final_decision_reason="nao deve passar da terceira linha",
            )
        )

        self.assertEqual(len(summary.splitlines()), 3)

    def test_workspace_consumes_telegram_admin_history(self):
        with patch("app.telegram.telegram_alert_engine.send_alert", return_value=True):
            send_signal_alert(_row(), now=1000, cooldown_seconds=1800)

        bootstrap = {
            "brand": "StockNewsBR",
            "pricing": {"trial_days": 30},
            "launch_roadmap": {"current": "web"},
            "ai_modules": [],
            "social_features": {},
        }
        metrics = {
            "engine_cycles": 1,
            "signals_generated": 1,
            "assets_scanned": 1,
            "cache_age": 0,
            "http_requests": 0,
            "ws_connections": 0,
            "chat_messages": 0,
        }

        with patch.object(workspace_service, "get_public_bootstrap", return_value=bootstrap), patch.object(
            workspace_service,
            "get_metrics_snapshot",
            return_value=metrics,
        ), patch.object(workspace_service, "get_snapshot", return_value={"signals": [], "ai_tools": {}, "symbol_snapshots": {}}), patch.object(
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
        ), patch.object(workspace_service.routes_system, "observability_dashboard", return_value={}):
            payload = workspace_service.get_workspace_data(user_id=7, channel="web")

        self.assertIn("telegram_alerts", payload)
        self.assertEqual(payload["telegram_alerts"]["latest"][0]["status"], "sent")
        self.assertEqual(payload["telegram_alerts"]["sent"][0]["reason"], "contratos finais justificam alerta institucional")

    def test_metrics_and_prometheus_expose_telegram_alerts(self):
        with patch("app.telegram.telegram_alert_engine.send_alert", return_value=True):
            send_signal_alert(_row(), now=1000, cooldown_seconds=1800)

        metrics = get_performance_metrics_snapshot()["telegram_alerts"]
        prometheus = format_prometheus_metrics()

        self.assertGreaterEqual(metrics["sent"], 1)
        self.assertGreaterEqual(metrics["critical"], 1)
        self.assertIn('telegram_alert_events_total{event="sent"}', prometheus)
        self.assertIn('telegram_alerts_total{level="critical"}', prometheus)

    def test_formatter_keeps_summary_product_ready(self):
        message = format_signal_alert(_row())

        self.assertIn("PETR4", message)
        self.assertIn("Confiança Histórica: 72.0%", message)
        self.assertLessEqual(len(telegram_summary(_row()).splitlines()), 3)
        self.assertTrue(get_telegram_alert_history(limit=1) == [])

    def test_legacy_telegram_access_fields_are_handled_fail_closed(self):
        # Mission 31F (CodeRabbit trivial): linhas antigas traziam os campos
        # planos telegram_linked/telegram_allowed em vez do contrato
        # telegram_access. A compatibilidade é fail-closed: sem o contrato
        # validado, o alerta é bloqueado de forma determinística e nada é
        # enviado — os campos legados sozinhos não concedem acesso.
        legacy_rows = {
            "legacy_allowed": ("LEGA3", {"telegram_linked": True, "telegram_allowed": True}),
            "legacy_denied": ("LEGB3", {"telegram_linked": True, "telegram_allowed": False}),
            "legacy_unlinked": ("LEGC3", {"telegram_linked": False, "telegram_allowed": False}),
        }

        for label, (ticker, legacy_fields) in legacy_rows.items():
            with self.subTest(label):
                row = _row(ticker=ticker, symbol=ticker, **legacy_fields)
                row.pop("telegram_access", None)

                with patch(
                    "app.telegram.telegram_alert_engine.send_alert",
                    side_effect=AssertionError("must_not_send"),
                ) as sender:
                    result = send_signal_alert(row, now=1000)

                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["reason"], "telegram_access_not_validated")
                sender.assert_not_called()

        with self.subTest("legacy_fields_do_not_break_modern_contract"):
            row = _row(ticker="LEGD3", symbol="LEGD3", telegram_linked=True, telegram_allowed=True)

            with patch("app.telegram.telegram_alert_engine.send_alert", return_value=True):
                result = send_signal_alert(row, now=1000)

            self.assertEqual(result["status"], "sent")


if __name__ == "__main__":
    unittest.main()
