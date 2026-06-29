import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.api import api_market_routes
from app.cache.snapshot_cache import SnapshotCache
from app.services import ranking
from app.services.snapshot_contract import (
    CANONICAL_DECISION_STATUSES,
    DECISION_BLOCKED,
    DECISION_CONFLICT,
    DECISION_INSUFFICIENT_DATA,
    DECISION_READY,
    DECISION_STALE_DATA,
    build_decision_envelope,
    is_actionable_snapshot_row,
)
from app.system import push_dispatcher
from app.system.performance_intelligence import calculate_performance_intelligence
from app.telegram import telegram_alert_engine


def _ready_row(**overrides):
    row = {
        "ticker": "PETR4",
        "symbol": "PETR4",
        "trade_action": "BUY",
        "signal": "BUY",
        "decision_ready": True,
        "decision_state": "BUY_READY",
        "price": 37.5,
        "volume": 1_000_000,
        "data_quality": "priced",
        "score_source_scale": "0_100",
        "master_score": 87.0,
        "master_score_raw": 87.0,
        "master_score_source_scale": "0_100",
        "master_direction": "BULLISH",
        "master_status": "APPROVED",
        "master_confidence": "Alta",
        "audit_status": "APPROVED",
        "operational_status": "READY",
        "ranking_eligible": True,
        "ranking_opportunity_score": 88.0,
        "ranking_opportunity_source_scale": "0_100",
        "final_decision": "OPORTUNIDADE CONFIRMADA",
        "final_decision_score": 92.0,
        "final_decision_summary": "Contexto institucional aprovado.",
        "source": "snapshot",
        "snapshot_id": "snap-29",
    }
    row.update(overrides)
    return row


class Mission29DecisionEnvelopeTests(unittest.TestCase):
    def test_ready_envelope_preserves_master_score_raw_and_display_contract(self):
        envelope = build_decision_envelope(_ready_row())

        self.assertEqual(envelope["decision_status"], DECISION_READY)
        self.assertTrue(envelope["decision_ready"])
        self.assertEqual(envelope["master_score"], 8.7)
        self.assertEqual(envelope["master_score_raw"], 87.0)
        self.assertEqual(envelope["source_snapshot_id"], "snap-29")
        self.assertIn(envelope["decision_status"], CANONICAL_DECISION_STATUSES)

    def test_price_volume_stale_conflict_and_auditor_blocks_are_canonical(self):
        cases = [
            (_ready_row(price=0), DECISION_INSUFFICIENT_DATA, "price_invalid"),
            (_ready_row(volume=0), DECISION_INSUFFICIENT_DATA, "volume_invalid"),
            (_ready_row(stale=True, data_quality="stale"), DECISION_STALE_DATA, "snapshot_stale"),
            (_ready_row(master_direction="BEARISH"), DECISION_CONFLICT, "decision_conflict"),
            (_ready_row(audit_status="BLOCKED", blocked_by_auditor=True), DECISION_BLOCKED, "auditor_blocked"),
        ]

        for row, expected_status, expected_blocker in cases:
            with self.subTest(expected_status=expected_status):
                envelope = build_decision_envelope(row)
                self.assertEqual(envelope["decision_status"], expected_status)
                self.assertFalse(envelope["decision_ready"])
                self.assertIn(expected_blocker, envelope["blockers"])
                self.assertIn(envelope["decision_status"], CANONICAL_DECISION_STATUSES)
                self.assertFalse(is_actionable_snapshot_row(row))

    def test_ranking_excludes_blocked_rows_and_returns_envelope_for_actionable_rows(self):
        ready = _ready_row()
        blocked = _ready_row(ticker="BLOQ1", symbol="BLOQ1", price=0, decision_ready=False)

        with patch.object(ranking, "get_snapshot_info", return_value={"signals": 2, "age_seconds": 1}), \
             patch.object(ranking, "get_snapshot_signals", return_value=[blocked, ready]), \
             patch.object(ranking, "ensure_final_decision_rows", side_effect=lambda rows: rows), \
             patch.object(ranking, "ensure_institutional_priority_rows", side_effect=lambda rows: rows), \
             patch.object(ranking, "ensure_institutional_conviction_rows", side_effect=lambda rows: rows), \
             patch.object(ranking, "ensure_operational_rules_rows", side_effect=lambda rows: rows), \
             patch.object(ranking, "ensure_historical_confidence_rows", side_effect=lambda rows: rows), \
             patch.object(ranking, "ensure_institutional_ranking_rows", side_effect=lambda rows: rows), \
             patch.object(ranking, "institutional_ranking_items", side_effect=lambda rows, limit=200: rows):
            payload = ranking.get_ranking(force_refresh=True)

        self.assertEqual([row["symbol"] for row in payload], ["PETR4"])
        self.assertEqual(payload[0]["decision_envelope"]["decision_status"], DECISION_READY)

    def test_telegram_and_push_do_not_dispatch_blocked_envelopes(self):
        blocked = _ready_row(price=0, decision_ready=False)

        with patch.object(telegram_alert_engine, "format_signal_alert") as formatter, patch.object(
            telegram_alert_engine,
            "send_alert",
        ) as sender:
            telegram_result = telegram_alert_engine.send_signal_alert(blocked)

        self.assertEqual(telegram_result["status"], "blocked")
        self.assertIn("decision_envelope=INSUFFICIENT_DATA", telegram_result["reason"])
        formatter.assert_not_called()
        sender.assert_not_called()
        self.assertEqual(push_dispatcher._eligible_signals([blocked]), [])

    def test_push_payload_carries_decision_envelope_for_ready_signal(self):
        class Query:
            def filter(self, *args, **kwargs):
                return self

            def all(self):
                return [SimpleNamespace(id=7)]

        class FakeDb:
            def query(self, _model):
                return Query()

            def close(self):
                return None

        with patch.object(push_dispatcher, "get_push_token_store", return_value={"7": ["token"]}), patch.object(
            push_dispatcher,
            "SessionLocal",
            return_value=FakeDb(),
        ), patch.object(push_dispatcher, "_load_state", return_value={}), patch.object(
            push_dispatcher,
            "_save_state",
        ), patch.object(push_dispatcher, "send_push_notification", return_value={"sent": 1}) as send_push:
            result = push_dispatcher.dispatch_signal_pushes([_ready_row()])

        self.assertEqual(result["sent"], 1)
        data = send_push.call_args.kwargs["data"]
        self.assertEqual(data["decision_status"], DECISION_READY)
        self.assertIn('"decision_status": "READY"', data["decision_envelope"])
        self.assertEqual(data["score"], "8.7")
        self.assertEqual(data["master_score"], "8.7")
        self.assertEqual(data["master_score_raw"], "87.0")
        self.assertEqual(data["master_score_raw_source_scale"], "0_100")
        self.assertEqual(data["master_score_source_scale"], "0_100")

    def test_snapshot_api_payload_keeps_legacy_fields_and_decision_envelope(self):
        cache = SnapshotCache()
        cache.update({"signals": [_ready_row()], "source": "test", "stale": False, "generated_at": "2026-06-15T12:00:00+00:00"})

        with patch.object(api_market_routes, "get_snapshot", return_value=cache.get()):
            payload = api_market_routes.snapshot()

        self.assertEqual(payload["signals"][0]["trade_action"], "BUY")
        self.assertEqual(payload["signals"][0]["decision_envelope"]["decision_status"], DECISION_READY)

    def test_performance_intelligence_groups_by_decision_status(self):
        payload = calculate_performance_intelligence(
            {
                "records": [
                    {
                        "ticker": "PETR4",
                        "status": "winner",
                        "simulated_result": "winner",
                        "actionability": True,
                        "decision_status": "READY",
                    },
                    {
                        "ticker": "VALE3",
                        "status": "blocked",
                        "simulated_result": "loser",
                        "actionability": False,
                        "decision_status": "CONFLICT",
                    },
                    {
                        "ticker": "ITUB4",
                        "status": "blocked",
                        "simulated_result": "neutral",
                        "actionability": False,
                        "decision_envelope": {"decision_status": "STALE_DATA"},
                    },
                ]
            }
        )

        self.assertEqual(payload["by_decision_status"]["READY"]["sample_size"], 1)
        self.assertEqual(payload["by_decision_status"]["CONFLICT"]["sample_size"], 1)
        self.assertEqual(payload["by_decision_status"]["STALE_DATA"]["sample_size"], 1)

    def test_frontend_contract_declares_decision_envelope_type(self):
        text = Path("apps/web/lib/types.ts").read_text(encoding="utf-8")

        self.assertIn("export type DecisionEnvelope", text)
        self.assertIn("decision_envelope?: DecisionEnvelope", text)


if __name__ == "__main__":
    unittest.main()
