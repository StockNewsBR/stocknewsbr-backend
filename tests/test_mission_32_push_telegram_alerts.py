# =====================================================
# MISSION 32 — PUSH, TELEGRAM E ALERTAS INSTITUCIONAIS
# =====================================================
# Certificação do pipeline de notificações: kill switches, isolamento de
# tokens, deduplicação determinística, idempotência, retry/backoff,
# classificação de erros, isolamento de canais, autorização e auditoria.
#
# Somente fake transports/mocks. Nenhum teste envia mensagem real.

import json
import os
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from app.ai.final_decision import FINAL_CONFIRMED, FINAL_FORMING
from app.ai.institutional_auditor import AUDIT_APPROVED
from app.ai.institutional_conviction import (
    CONVICTION_HIGH,
    CONVICTION_MODERATE,
    CONVICTION_VERY_HIGH,
)
from app.ai.institutional_priority import (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
)
from app.ai.operational_rules import OPERATIONAL_READY
from app.services import push_service as ps
from app.system import kill_switches as ks
from app.system import push_dispatcher as pd_mod
from app.system.paper_trading import PAPER_TRADING_MODE
from app.telegram import telegram_alert_engine as eng
from app.telegram.telegram_alert_formatter import format_signal_alert


REPO_ROOT = Path(__file__).resolve().parents[1]

KS_ENV_VARS = [
    "DISABLE_PUSH_ALERTS",
    "DISABLE_TELEGRAM_ALERTS",
    "DISABLE_AI_DECISIONS",
    "READ_ONLY_MODE",
    "DISABLE_PROVIDER_ALPACA",
    "DISABLE_PROVIDER_BINANCE",
    "DISABLE_SYMBOL_PETR4",
    "DISABLE_SYMBOL_BTC_USD",
]

TOKEN_A = "fake-device-token-user-a-0000000001"
TOKEN_B = "fake-device-token-user-b-0000000002"


def _clear_kill_switch_env():
    for name in KS_ENV_VARS:
        os.environ.pop(name, None)


class _EnvCleanMixin(unittest.TestCase):
    def setUp(self):
        super().setUp()
        _clear_kill_switch_env()
        self.addCleanup(_clear_kill_switch_env)


class _PushStoreMixin(_EnvCleanMixin):
    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        store_path = Path(self._tmp.name) / "push_tokens.json"
        patcher = patch.object(ps, "PUSH_STORE_PATH", store_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store_path = store_path


# =====================================================
# KILL SWITCHES (32-20)
# =====================================================

class KillSwitchTests(_EnvCleanMixin):
    def test_defaults_are_all_off(self):
        self.assertFalse(ks.is_push_alerts_disabled())
        self.assertFalse(ks.is_telegram_alerts_disabled())
        self.assertFalse(ks.is_ai_decisions_disabled())
        self.assertFalse(ks.is_read_only_mode())
        self.assertIsNone(ks.alert_channel_block_reason("push"))
        self.assertIsNone(ks.alert_channel_block_reason("telegram"))

    def test_truthy_values_enable_switch(self):
        for value in ("1", "true", "TRUE", "yes", "on", "enabled"):
            os.environ["DISABLE_PUSH_ALERTS"] = value
            self.assertTrue(ks.is_push_alerts_disabled(), value)
        for value in ("0", "false", "", "off", "no"):
            os.environ["DISABLE_PUSH_ALERTS"] = value
            self.assertFalse(ks.is_push_alerts_disabled(), repr(value))

    def test_rollback_is_immediate(self):
        os.environ["DISABLE_TELEGRAM_ALERTS"] = "1"
        self.assertTrue(ks.is_telegram_alerts_disabled())
        os.environ.pop("DISABLE_TELEGRAM_ALERTS")
        self.assertFalse(ks.is_telegram_alerts_disabled())

    def test_channel_block_reasons(self):
        os.environ["DISABLE_PUSH_ALERTS"] = "1"
        self.assertEqual(ks.alert_channel_block_reason("push"), "kill_switch=DISABLE_PUSH_ALERTS")
        self.assertIsNone(ks.alert_channel_block_reason("telegram"))
        os.environ.pop("DISABLE_PUSH_ALERTS")

        os.environ["DISABLE_TELEGRAM_ALERTS"] = "1"
        self.assertEqual(ks.alert_channel_block_reason("telegram"), "kill_switch=DISABLE_TELEGRAM_ALERTS")
        self.assertIsNone(ks.alert_channel_block_reason("push"))

    def test_read_only_mode_blocks_both_channels(self):
        os.environ["READ_ONLY_MODE"] = "1"
        self.assertEqual(ks.alert_channel_block_reason("push"), "kill_switch=READ_ONLY_MODE")
        self.assertEqual(ks.alert_channel_block_reason("telegram"), "kill_switch=READ_ONLY_MODE")

    def test_kill_switch_read_error_fails_closed(self):
        with patch.object(ks.os, "getenv", side_effect=RuntimeError("env unavailable")):
            self.assertEqual(
                ks.alert_channel_block_reason("push"),
                "kill_switch=EVALUATION_ERROR_FAIL_SAFE",
            )
            self.assertEqual(
                ks.symbol_block_reason("PETR4"),
                "kill_switch=EVALUATION_ERROR_FAIL_SAFE",
            )

    def test_provider_and_symbol_switches_with_normalization(self):
        os.environ["DISABLE_PROVIDER_ALPACA"] = "1"
        os.environ["DISABLE_SYMBOL_PETR4"] = "1"
        os.environ["DISABLE_SYMBOL_BTC_USD"] = "1"
        self.assertTrue(ks.is_provider_disabled("alpaca"))
        self.assertTrue(ks.is_provider_disabled("Alpaca"))
        self.assertFalse(ks.is_provider_disabled("binance"))
        self.assertTrue(ks.is_symbol_disabled("petr4"))
        self.assertTrue(ks.is_symbol_disabled("BTC-USD"))
        self.assertFalse(ks.is_symbol_disabled("VALE3"))
        self.assertFalse(ks.is_symbol_disabled(""))
        self.assertIn("DISABLE_SYMBOL_PETR4", ks.symbol_block_reason("PETR4"))

    def test_status_snapshot_is_auditable_and_paper_only(self):
        os.environ["DISABLE_PROVIDER_BINANCE"] = "1"
        os.environ["DISABLE_SYMBOL_PETR4"] = "1"
        status = ks.get_kill_switch_status()
        self.assertFalse(status["DISABLE_PUSH_ALERTS"])
        self.assertIn("DISABLE_PROVIDER_BINANCE", status["providers_disabled"])
        self.assertIn("DISABLE_SYMBOL_PETR4", status["symbols_disabled"])
        self.assertEqual(status["PAPER_ONLY"], "PAPER_ONLY")
        self.assertEqual(PAPER_TRADING_MODE, "PAPER_ONLY")


# =====================================================
# PUSH TOKEN STORE (32-01, 32-02, 32-18)
# =====================================================

class PushTokenStoreTests(_PushStoreMixin):
    def test_register_isolates_tokens_per_user(self):
        ps.register_push_token(1, TOKEN_A, "android")
        ps.register_push_token(2, TOKEN_B, "android")
        tokens_a = ps.list_push_tokens(1)
        tokens_b = ps.list_push_tokens(2)
        self.assertEqual([item["token"] for item in tokens_a], [TOKEN_A])
        self.assertEqual([item["token"] for item in tokens_b], [TOKEN_B])

    def test_public_responses_never_expose_raw_token(self):
        result = ps.register_push_token(1, TOKEN_A, "android")
        payload = json.dumps(result)
        self.assertNotIn(TOKEN_A, payload)
        self.assertIn("token_masked", payload)

        public_items = ps.list_push_tokens_public(1)
        self.assertNotIn(TOKEN_A, json.dumps(public_items))
        self.assertTrue(all("token" not in item for item in public_items))

        removal = ps.unregister_push_token(1, TOKEN_A)
        self.assertNotIn(TOKEN_A, json.dumps(removal))

    def test_mask_token_format(self):
        masked = ps.mask_push_token(TOKEN_A)
        self.assertIn("...", masked)
        self.assertNotEqual(masked, TOKEN_A)
        self.assertLess(len(masked), len(TOKEN_A))
        self.assertEqual(ps.mask_push_token("short"), "***")
        self.assertEqual(ps.mask_push_token(None), "***")

    def test_same_token_rebinds_to_last_user(self):
        ps.register_push_token(1, TOKEN_A, "android")
        ps.register_push_token(2, TOKEN_A, "android")
        self.assertEqual(ps.list_push_tokens(1), [])
        self.assertEqual([item["token"] for item in ps.list_push_tokens(2)], [TOKEN_A])
        store = ps.get_push_token_store()
        occurrences = sum(
            1 for items in store.values() for item in items if item.get("token") == TOKEN_A
        )
        self.assertEqual(occurrences, 1)

    def test_reregister_same_user_rotates_entry(self):
        ps.register_push_token(1, TOKEN_A, "android")
        ps.register_push_token(1, TOKEN_A, "android", app_version="2.0")
        items = ps.list_push_tokens(1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["app_version"], "2.0")

    def test_store_caps_at_ten_tokens(self):
        for index in range(12):
            ps.register_push_token(1, f"fake-token-{index:02d}-{'x' * 24}", "android")
        self.assertEqual(len(ps.list_push_tokens(1)), 10)

    def test_invalid_inputs_rejected(self):
        self.assertIsNone(ps.register_push_token(0, TOKEN_A, "android"))
        self.assertIsNone(ps.register_push_token(1, "", "android"))
        self.assertIsNone(ps.register_push_token(1, "   ", "android"))

    def test_unregister_removes_token(self):
        ps.register_push_token(1, TOKEN_A, "android")
        ps.unregister_push_token(1, TOKEN_A)
        self.assertEqual(ps.list_push_tokens(1), [])

    def test_deactivate_marks_inactive_preserving_evidence(self):
        ps.register_push_token(1, TOKEN_A, "android")
        changed = ps.deactivate_push_token(1, TOKEN_A, reason="UnregisteredError")
        self.assertTrue(changed)
        self.assertEqual(ps.list_push_tokens(1), [])
        archived = ps.list_push_tokens(1, include_inactive=True)
        self.assertEqual(len(archived), 1)
        self.assertFalse(archived[0]["active"])
        self.assertEqual(archived[0]["deactivated_reason"], "UnregisteredError")
        self.assertIn("deactivated_at", archived[0])

    def test_reregistration_after_deactivation_reactivates(self):
        ps.register_push_token(1, TOKEN_A, "android")
        ps.deactivate_push_token(1, TOKEN_A)
        ps.register_push_token(1, TOKEN_A, "android")
        active = ps.list_push_tokens(1)
        self.assertEqual(len(active), 1)
        self.assertTrue(active[0]["active"])

    def test_concurrent_registration_of_same_token_yields_single_owner(self):
        barrier = threading.Barrier(2)

        def register(user_id):
            barrier.wait(timeout=5)
            ps.register_push_token(user_id, TOKEN_A, "android")

        threads = [threading.Thread(target=register, args=(uid,)) for uid in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        store = ps.get_push_token_store()
        occurrences = sum(
            1 for items in store.values() for item in items if item.get("token") == TOKEN_A
        )
        self.assertEqual(occurrences, 1)


# =====================================================
# PUSH SEND — FAKE TRANSPORT, RETRY E CLASSIFICAÇÃO (32-11, 32-18)
# =====================================================

class PushSendTests(_PushStoreMixin):
    def test_fake_sender_success_counts_sends(self):
        ps.register_push_token(1, TOKEN_A, "android")
        ps.register_push_token(1, TOKEN_B, "android")
        calls = []

        def sender(token, title, body, data):
            calls.append(token)

        result = ps.send_push_notification(1, "t", "b", sender=sender)
        self.assertEqual(result["sent"], 2)
        self.assertEqual(result["tokens"], 2)
        self.assertEqual(sorted(calls), sorted([TOKEN_A, TOKEN_B]))

    def test_invalid_token_deactivated_without_retry(self):
        ps.register_push_token(1, TOKEN_A, "android")
        ps.register_push_token(1, TOKEN_B, "android")
        attempts = []

        def sender(token, title, body, data):
            attempts.append(token)
            if token == TOKEN_A:
                raise ps.PushTokenInvalidError("registration-token-not-registered")

        result = ps.send_push_notification(1, "t", "b", sender=sender)
        self.assertEqual(result["sent"], 1)
        self.assertEqual(result["invalidated"], 1)
        # Uma única tentativa por token — sem retry do token inválido.
        self.assertEqual(attempts.count(TOKEN_A), 1)
        # Somente o token afetado foi desativado.
        active = [item["token"] for item in ps.list_push_tokens(1)]
        self.assertEqual(active, [TOKEN_B])
        # Ciclo seguinte não tenta mais o token inválido.
        attempts.clear()
        result2 = ps.send_push_notification(1, "t", "b", sender=sender)
        self.assertEqual(result2["tokens"], 1)
        self.assertNotIn(TOKEN_A, attempts)

    def test_firebase_named_errors_classified_as_invalid(self):
        class UnregisteredError(Exception):
            pass

        ps.register_push_token(1, TOKEN_A, "android")

        def sender(token, title, body, data):
            raise UnregisteredError("token gone")

        result = ps.send_push_notification(1, "t", "b", sender=sender)
        self.assertEqual(result["invalidated"], 1)
        archived = ps.list_push_tokens(1, include_inactive=True)
        self.assertFalse(archived[0]["active"])
        self.assertEqual(archived[0]["deactivated_reason"], "UnregisteredError")

    def test_temporary_failure_does_not_deactivate_token(self):
        ps.register_push_token(1, TOKEN_A, "android")

        def sender(token, title, body, data):
            raise ps.PushSendError("HTTP 503 provider unavailable")

        result = ps.send_push_notification(1, "t", "b", sender=sender)
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["invalidated"], 0)
        self.assertTrue(ps.list_push_tokens(1)[0]["active"])

    def test_kill_switch_blocks_send_with_auditable_reason(self):
        ps.register_push_token(1, TOKEN_A, "android")
        os.environ["DISABLE_PUSH_ALERTS"] = "1"
        called = []

        result = ps.send_push_notification(1, "t", "b", sender=lambda *a: called.append(a))
        self.assertEqual(result["sent"], 0)
        self.assertIn("kill_switch=DISABLE_PUSH_ALERTS", result["reason"])
        self.assertEqual(called, [])

    def test_read_only_mode_blocks_send(self):
        ps.register_push_token(1, TOKEN_A, "android")
        os.environ["READ_ONLY_MODE"] = "true"
        result = ps.send_push_notification(1, "t", "b", sender=lambda *a: None)
        self.assertEqual(result["sent"], 0)
        self.assertIn("READ_ONLY_MODE", result["reason"])

    def test_no_tokens_returns_explicit_reason(self):
        result = ps.send_push_notification(99, "t", "b", sender=lambda *a: None)
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["reason"], "no_registered_tokens")

    def test_firebase_not_configured_fails_closed(self):
        ps.register_push_token(1, TOKEN_A, "android")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            os.environ.pop("FIREBASE_SERVICE_ACCOUNT_JSON", None)
            result = ps.send_push_notification(1, "t", "b")
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["reason"], "firebase_not_configured")


# =====================================================
# PUSH DISPATCHER — KILL SWITCH, COOLDOWN, AUDITORIA (32-08, 32-09, 32-20)
# =====================================================

class _FakeQuery:
    def __init__(self, users):
        self._users = users

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self._users


class _FakeSession:
    def __init__(self, users):
        self._users = users

    def query(self, *args):
        return _FakeQuery(self._users)

    def close(self):
        pass


class _FakeUser:
    def __init__(self, user_id):
        self.id = user_id


class PushDispatcherTests(_EnvCleanMixin):
    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        state_path = Path(self._tmp.name) / "push_dispatch_state.json"
        for patcher in (
            patch.object(pd_mod, "PUSH_DISPATCH_STATE_PATH", state_path),
            patch.object(pd_mod, "SessionLocal", lambda: _FakeSession([_FakeUser(1)])),
            patch.object(pd_mod, "get_push_token_store", lambda: {"1": [{"token": TOKEN_A, "active": True}]}),
            patch.object(pd_mod, "build_decision_envelope", lambda signal: {"decision_status": "READY"}),
            patch.object(
                pd_mod,
                "attach_master_score_display_contract",
                lambda signal: {"master_score": 9.0, "master_score_source_scale": "0_100", "master_score_raw": 90.0},
            ),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.state_path = state_path
        self.signal = {"ticker": "PETR4"}

    def _patch_eligible(self):
        patcher = patch.object(pd_mod, "_eligible_signals", lambda signals: list(signals))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_kill_switch_blocks_dispatch_before_any_send(self):
        os.environ["DISABLE_PUSH_ALERTS"] = "1"
        sends = []
        with patch.object(pd_mod, "send_push_notification", lambda **kw: sends.append(kw) or {"sent": 1}):
            result = pd_mod.dispatch_signal_pushes([self.signal])
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["blocked_by"], "kill_switch=DISABLE_PUSH_ALERTS")
        self.assertEqual(sends, [])

    def test_read_only_mode_blocks_dispatch(self):
        os.environ["READ_ONLY_MODE"] = "on"
        result = pd_mod.dispatch_signal_pushes([self.signal])
        self.assertEqual(result.get("blocked_by"), "kill_switch=READ_ONLY_MODE")

    def test_symbol_kill_switch_skips_only_that_symbol(self):
        self._patch_eligible()
        os.environ["DISABLE_SYMBOL_PETR4"] = "1"
        sends = []
        with patch.object(
            pd_mod,
            "send_push_notification",
            lambda **kw: sends.append(kw.get("data", {}).get("ticker")) or {"sent": 1},
        ):
            result = pd_mod.dispatch_signal_pushes([{"ticker": "PETR4"}, {"ticker": "VALE3"}])
        self.assertNotIn("PETR4", sends)
        self.assertIn("VALE3", sends)
        self.assertEqual(result["sent"], 1)

    def test_cooldown_blocks_resend_and_state_persists(self):
        self._patch_eligible()
        sends = []
        with patch.object(pd_mod, "send_push_notification", lambda **kw: sends.append(1) or {"sent": 1}):
            first = pd_mod.dispatch_signal_pushes([self.signal])
            second = pd_mod.dispatch_signal_pushes([self.signal])
        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["sent"], 0)
        self.assertEqual(len(sends), 1)
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertIn("PETR4", state)

    def test_failed_send_does_not_mark_cooldown(self):
        # Alerta que falhou não pode ser "perdido": sem cooldown gravado,
        # o ciclo seguinte re-tenta.
        self._patch_eligible()
        results = iter([{"sent": 0}, {"sent": 1}])
        calls = []
        with patch.object(pd_mod, "send_push_notification", lambda **kw: calls.append(1) or next(results)):
            first = pd_mod.dispatch_signal_pushes([self.signal])
            second = pd_mod.dispatch_signal_pushes([self.signal])
        self.assertEqual(first["sent"], 0)
        self.assertEqual(second["sent"], 1)
        self.assertEqual(len(calls), 2)

    def test_kill_switch_does_not_alter_historical_state(self):
        self.state_path.write_text(json.dumps({"PETR4": 12345}), encoding="utf-8")
        os.environ["DISABLE_PUSH_ALERTS"] = "1"
        pd_mod.dispatch_signal_pushes([self.signal])
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state, {"PETR4": 12345})


# =====================================================
# TELEGRAM ENGINE — GATES, DEDUP, IDEMPOTÊNCIA (32-03, 32-04, 32-08 a 32-12)
# =====================================================

def _ready_signal(**overrides):
    signal = {
        "ticker": "PETR4",
        "final_decision": FINAL_CONFIRMED,
        "priority_level": PRIORITY_CRITICAL,
        "conviction_level": CONVICTION_VERY_HIGH,
        "operational_status": OPERATIONAL_READY,
        "audit_status": AUDIT_APPROVED,
        "decision_ready": True,
        "telegram_access": {"allowed": True},
    }
    signal.update(overrides)
    return signal


class TelegramEngineGateTests(_EnvCleanMixin):
    def setUp(self):
        super().setUp()
        eng.reset_telegram_alert_state()
        self.addCleanup(eng.reset_telegram_alert_state)

    def test_kill_switch_blocks_telegram_alert_with_audit(self):
        os.environ["DISABLE_TELEGRAM_ALERTS"] = "1"
        result = eng.send_signal_alert({"ticker": "PETR4"})
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "kill_switch=DISABLE_TELEGRAM_ALERTS")
        history = eng.get_telegram_alert_history(limit=5)
        self.assertTrue(any(item["reason"] == "kill_switch=DISABLE_TELEGRAM_ALERTS" for item in history))

    def test_read_only_mode_blocks_telegram(self):
        os.environ["READ_ONLY_MODE"] = "1"
        result = eng.build_telegram_alert({"ticker": "PETR4"})
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "kill_switch=READ_ONLY_MODE")

    def test_symbol_kill_switch_blocks_specific_symbol(self):
        os.environ["DISABLE_SYMBOL_PETR4"] = "1"
        blocked = eng.build_telegram_alert({"ticker": "PETR4"})
        self.assertEqual(blocked["status"], "blocked")
        self.assertIn("DISABLE_SYMBOL_PETR4", blocked["reason"])
        other = eng.build_telegram_alert({"ticker": "VALE3"})
        self.assertNotIn("kill_switch", str(other.get("reason")))

    def test_missing_ticker_discarded(self):
        result = eng.build_telegram_alert({})
        self.assertEqual(result["status"], "discarded")
        self.assertEqual(result["reason"], "missing_ticker")

    def test_insufficient_data_blocked_by_decision_envelope(self):
        # Sinal sem contratos institucionais: nunca envia, motivo auditável.
        result = eng.build_telegram_alert({"ticker": "PETR4"})
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(str(result["reason"]).startswith("decision_envelope="))

    def test_access_not_validated_blocks(self):
        with patch.object(eng, "_blocking_reason", lambda signal: None):
            signal = _ready_signal()
            signal.pop("telegram_access")
            result = eng.build_telegram_alert(signal)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "telegram_access_not_validated")

    def test_linked_but_not_allowed_blocks(self):
        with patch.object(eng, "_blocking_reason", lambda signal: None):
            result = eng.build_telegram_alert(
                _ready_signal(telegram_access={"allowed": False, "reason": "telegram_access_required"})
            )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "telegram_access_required")

    def test_allowed_signal_becomes_ready_with_fingerprint(self):
        with patch.object(eng, "_blocking_reason", lambda signal: None):
            result = eng.build_telegram_alert(_ready_signal())
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["alert_level"], eng.ALERT_CRITICAL)
        self.assertTrue(result["fingerprint"])

    def test_classification_levels(self):
        self.assertEqual(eng.classify_telegram_alert(_ready_signal()), eng.ALERT_CRITICAL)
        self.assertEqual(
            eng.classify_telegram_alert(
                _ready_signal(priority_level=PRIORITY_HIGH, conviction_level=CONVICTION_HIGH)
            ),
            eng.ALERT_HIGH,
        )
        self.assertEqual(
            eng.classify_telegram_alert(
                _ready_signal(
                    final_decision=FINAL_FORMING,
                    priority_level=PRIORITY_MEDIUM,
                    conviction_level=CONVICTION_MODERATE,
                )
            ),
            eng.ALERT_MEDIUM,
        )
        self.assertIsNone(eng.classify_telegram_alert(_ready_signal(final_decision="???")))


class TelegramDispatchTests(_EnvCleanMixin):
    def setUp(self):
        super().setUp()
        eng.reset_telegram_alert_state()
        self.addCleanup(eng.reset_telegram_alert_state)
        self.signal = {"ticker": "PETR4"}
        self.prepared = {"alert_level": eng.ALERT_HIGH, "fingerprint": "FP-TEST-1"}

    def _dispatch(self, transport_status="sent", now=1000.0, prepared=None, transport_log=None):
        log = transport_log if transport_log is not None else []

        def fake_transport(message):
            log.append(message)
            return transport_status

        with patch.object(eng, "_send_alert_transport", fake_transport):
            result = eng._dispatch_prepared_alert(
                self.signal,
                dict(prepared or self.prepared),
                now=now,
                cooldown_seconds=60,
            )
        return result, log

    def test_sent_then_deduplicated(self):
        first, log1 = self._dispatch(now=1000.0)
        self.assertEqual(first["status"], "sent")
        second, log2 = self._dispatch(now=1010.0)
        self.assertEqual(second["status"], "deduplicated")
        self.assertEqual(len(log2), 0)

    def test_equivalent_alert_hits_cooldown(self):
        self._dispatch(now=1000.0)
        prepared2 = {"alert_level": eng.ALERT_HIGH, "fingerprint": "FP-TEST-2"}
        result, log = self._dispatch(now=1010.0, prepared=prepared2)
        self.assertEqual(result["status"], "cooldown")
        self.assertGreater(result["cooldown_remaining_seconds"], 0)
        self.assertEqual(len(log), 0)

    def test_expired_window_allows_resend(self):
        self._dispatch(now=1000.0)
        result, log = self._dispatch(now=2000.0)
        self.assertEqual(result["status"], "sent")

    def test_failed_send_releases_reservation_for_retry(self):
        first, log1 = self._dispatch(transport_status="failed", now=1000.0)
        self.assertEqual(first["status"], "error")
        self.assertEqual(first["reason"], "telegram_send_failed")
        second, log2 = self._dispatch(transport_status="sent", now=1001.0)
        self.assertEqual(second["status"], "sent")

    def test_unknown_timeout_keeps_reservation_no_duplicate(self):
        # Timeout ambíguo: resultado UNKNOWN (nunca DELIVERED) e nenhum
        # re-envio automático que poderia duplicar o alerta.
        transport_log = []
        first, _ = self._dispatch(transport_status="unknown", now=1000.0, transport_log=transport_log)
        self.assertEqual(first["status"], "unknown")
        self.assertEqual(first["reason"], "telegram_send_timeout_ambiguous")
        second, _ = self._dispatch(transport_status="sent", now=1010.0, transport_log=transport_log)
        self.assertEqual(second["status"], "deduplicated")
        self.assertEqual(len(transport_log), 1)

    def test_concurrent_dispatch_same_fingerprint_sends_once(self):
        barrier = threading.Barrier(2)
        results = []
        transport_calls = []
        lock = threading.Lock()

        def fake_transport(message):
            with lock:
                transport_calls.append(message)
            return "sent"

        # patch aplicado uma única vez para as duas threads
        patcher = patch.object(eng, "_send_alert_transport", fake_transport)
        patcher.start()
        self.addCleanup(patcher.stop)

        def run_dispatch():
            barrier.wait(timeout=5)
            result = eng._dispatch_prepared_alert(
                self.signal,
                dict(self.prepared),
                now=1000.0,
                cooldown_seconds=60,
            )
            with lock:
                results.append(result["status"])

        threads = [threading.Thread(target=run_dispatch) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(sorted(results), ["deduplicated", "sent"])
        self.assertEqual(len(transport_calls), 1)

    def test_no_alert_lost_silently_every_outcome_audited(self):
        eng.reset_telegram_alert_state()
        self._dispatch(now=1000.0)                      # sent
        self._dispatch(now=1010.0)                      # deduplicated
        prepared2 = {"alert_level": eng.ALERT_HIGH, "fingerprint": "FP-X"}
        self._dispatch(now=1010.0, prepared=prepared2)  # cooldown
        history = eng.get_telegram_alert_history(limit=10)
        statuses = [item["status"] for item in history]
        self.assertIn("sent", statuses)
        self.assertIn("deduplicated", statuses)
        self.assertIn("cooldown", statuses)

    def test_bulk_mixed_and_batch_limit(self):
        transport = []
        with patch.object(eng, "_blocking_reason", lambda signal: None), patch.object(
            eng, "_send_alert_transport", lambda message: transport.append(message) or "sent"
        ):
            signals = [
                {},  # discarded: missing ticker
                _ready_signal(ticker="PETR4"),
                _ready_signal(ticker="VALE3"),
                _ready_signal(ticker="ITUB4"),
            ]
            summary = eng.send_bulk_alert(signals, now=1000.0, cooldown_seconds=60, max_alerts=2)
        self.assertEqual(summary["discarded"], 2)  # missing ticker + batch overflow
        self.assertEqual(summary["sent"], 2)
        self.assertEqual(len(transport), 2)

    def test_health_exposes_kill_switch_and_counters(self):
        os.environ["DISABLE_TELEGRAM_ALERTS"] = "1"
        health = eng.get_telegram_health()
        self.assertTrue(health["kill_switches"]["telegram_alerts_disabled"])
        self.assertEqual(
            health["kill_switches"]["block_reason"], "kill_switch=DISABLE_TELEGRAM_ALERTS"
        )
        for key in ("sent", "blocked", "discarded", "deduplicated", "cooldown", "errors"):
            self.assertIsInstance(health[key], int)


# =====================================================
# TELEGRAM TRANSPORT — SEGURANÇA E RETRY (32-11, 32-14, 32-15)
# =====================================================

class _FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


class TelegramTransportTests(_EnvCleanMixin):
    FAKE_TOKEN = "0000000000:FAKE-synthetic-token-for-tests-only"
    FAKE_CHAT = "-1000000000000"

    def setUp(self):
        super().setUp()
        for patcher in (
            patch.object(eng, "TELEGRAM_TOKEN", self.FAKE_TOKEN),
            patch.object(eng, "CHAT_ID", self.FAKE_CHAT),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        eng._last_alert_time = 0.0

    def test_not_configured_fails_closed(self):
        with patch.object(eng, "TELEGRAM_TOKEN", ""):
            self.assertEqual(eng._send_alert_transport("msg"), eng.TRANSPORT_FAILED)
            self.assertEqual(eng.send_alert("msg"), eng.TRANSPORT_FAILED)
        # Compatibilidade com mocks booleanos legados no seam send_alert.
        self.assertEqual(eng._coerce_transport_status(True), eng.TRANSPORT_SENT)
        self.assertEqual(eng._coerce_transport_status(False), eng.TRANSPORT_FAILED)
        self.assertEqual(eng._coerce_transport_status("unknown"), eng.TRANSPORT_UNKNOWN)

    def test_payload_is_plain_text_without_parse_mode(self):
        captured = {}

        def fake_post(url, json=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            return _FakeResponse(200)

        with patch.object(eng._session, "post", fake_post):
            status = eng._send_alert_transport("alerta *_[]<>&` PETR4")
        self.assertEqual(status, eng.TRANSPORT_SENT)
        self.assertNotIn("parse_mode", captured["json"])
        self.assertIn("PETR4", captured["json"]["text"])

    def test_message_truncated_to_4000_chars(self):
        captured = {}

        def fake_post(url, json=None, timeout=None):
            captured["json"] = json
            return _FakeResponse(200)

        with patch.object(eng._session, "post", fake_post):
            eng._send_alert_transport("x" * 9000)
        self.assertEqual(len(captured["json"]["text"]), 4000)

    def test_http_error_returns_failed(self):
        with patch.object(eng._session, "post", lambda *a, **k: _FakeResponse(400)):
            self.assertEqual(eng._send_alert_transport("msg"), eng.TRANSPORT_FAILED)

    def test_read_timeout_returns_unknown(self):
        def fake_post(*args, **kwargs):
            raise requests.exceptions.ReadTimeout("read timed out")

        with patch.object(eng._session, "post", fake_post):
            self.assertEqual(eng._send_alert_transport("msg"), eng.TRANSPORT_UNKNOWN)

    def test_connection_error_returns_failed(self):
        def fake_post(*args, **kwargs):
            raise requests.exceptions.ConnectionError("boom")

        with patch.object(eng._session, "post", fake_post):
            self.assertEqual(eng._send_alert_transport("msg"), eng.TRANSPORT_FAILED)

    def test_bot_token_never_logged_on_exception(self):
        def fake_post(url, json=None, timeout=None):
            raise requests.exceptions.ConnectionError(f"failed to reach {url}")

        with patch.object(eng._session, "post", fake_post):
            with self.assertLogs("stocknewsbr.telegram", level="ERROR") as logs:
                eng._send_alert_transport("msg")
        joined = "\n".join(logs.output)
        self.assertNotIn(self.FAKE_TOKEN, joined)
        self.assertIn("***TELEGRAM_TOKEN***", joined)

    def test_scrub_secret_masks_token_and_chat(self):
        raw = f"url https://api.telegram.org/bot{self.FAKE_TOKEN}/sendMessage chat {self.FAKE_CHAT}"
        scrubbed = eng._scrub_secret(raw)
        self.assertNotIn(self.FAKE_TOKEN, scrubbed)
        self.assertNotIn(self.FAKE_CHAT, scrubbed)

    def test_retry_policy_limited_with_backoff_and_no_400(self):
        self.assertEqual(eng.retry.total, 3)
        self.assertGreater(eng.retry.backoff_factor, 0)
        self.assertIn(429, eng.retry.status_forcelist)
        self.assertIn(500, eng.retry.status_forcelist)
        self.assertNotIn(400, eng.retry.status_forcelist)
        self.assertNotIn(401, eng.retry.status_forcelist)
        if hasattr(eng.retry, "backoff_jitter"):
            self.assertGreater(eng.retry.backoff_jitter, 0)


# =====================================================
# TEMPLATES (32-07, 32-15)
# =====================================================

class TemplateTests(_EnvCleanMixin):
    def test_action_in_message_matches_payload_action(self):
        for action in ("BUY", "SELL", "SHORT", "COVER", "WATCH", "HOLD", "NO_TRADE"):
            message = format_signal_alert({"ticker": "PETR4", "final_decision": action})
            self.assertTrue(message.startswith(action), message[:40])

    def test_missing_data_renders_na_never_none(self):
        message = format_signal_alert({"ticker": "PETR4"})
        self.assertIn("N/A", message)
        self.assertNotIn("None", message)
        self.assertNotIn("NaN", message)
        self.assertNotIn("undefined", message)

    def test_score_public_scale_0_10(self):
        message = format_signal_alert({"ticker": "PETR4", "master_score_raw": 85, "master_score_source_scale": "0_100"})
        self.assertIn("Score Mestre: 8.5", message)
        self.assertNotIn("Score Mestre: 85", message)

    def test_invalid_score_renders_na(self):
        message = format_signal_alert({"ticker": "PETR4", "master_score": "not-a-number"})
        self.assertIn("Score Mestre: N/A", message)

    def test_crypto_and_b3_tickers(self):
        # O formatter usa sempre o símbolo canônico do registry.
        for ticker, canonical in (("PETR4", "PETR4"), ("BTC-USD", "BTCUSD")):
            message = format_signal_alert({"ticker": ticker, "final_decision": "WATCH"})
            self.assertIn(canonical, message)

    def test_special_characters_survive_plain_text(self):
        summary = "risco <alto> & retorno _forte_ *agora* [link] `code`"
        message = format_signal_alert({"ticker": "PETR4", "telegram_summary": summary})
        self.assertIn("<alto>", message)
        self.assertIn("&", message)

    def test_long_text_is_bounded_by_summary_lines(self):
        long_line = "linha muito longa " * 40
        message = format_signal_alert({"ticker": "PETR4", "telegram_summary": long_line})
        self.assertLess(len(message), 1200)


# =====================================================
# AUTORIZAÇÃO DAS ROTAS (32-17) — verificação estática de contrato
# =====================================================

class RouteAuthorizationTests(unittest.TestCase):
    def _source(self, relative):
        return (REPO_ROOT / relative).read_text(encoding="utf-8")

    def test_push_routes_require_authentication(self):
        source = self._source("app/api/routes_push.py")
        for route in ("push_status", "push_tokens", "push_register", "push_unregister"):
            self.assertIn("require_active_plan", source)
        self.assertIn("require_internal_token", source)
        # Endpoint de teste jamais aberto a usuário comum.
        test_send_block = source.split("push_test_send")[1]
        self.assertIn("require_internal_token", test_send_block)

    def test_push_tokens_route_uses_masked_listing(self):
        source = self._source("app/api/routes_push.py")
        self.assertIn("list_push_tokens_public", source)
        self.assertNotIn("list_push_tokens(current_user", source)

    def test_internal_telegram_routes_require_internal_token(self):
        source = self._source("app/api/routes_internal.py")
        self.assertIn("dependencies=[Depends(require_internal_token)]", source)

    def test_system_status_requires_internal_token_and_exposes_kill_switches(self):
        source = self._source("app/api/routes_system.py")
        self.assertIn("dependencies=[Depends(require_internal_token)]", source)
        self.assertIn("get_kill_switch_status", source)

    def test_worker_channels_have_independent_error_isolation(self):
        source = self._source("worker.py")
        self.assertIn('logger.exception("Push dispatch error")', source)
        self.assertIn('logger.exception("Telegram dispatch error")', source)
        push_index = source.index("dispatch_signal_pushes(snapshot_signals)")
        telegram_index = source.index("send_bulk_alert(snapshot_signals)")
        push_handler = source.index('logger.exception("Push dispatch error")')
        self.assertLess(push_index, push_handler)
        self.assertLess(push_handler, telegram_index)


# =====================================================
# ISOLAMENTO DE CANAIS (32-12)
# =====================================================

class ChannelIsolationTests(_PushStoreMixin):
    def setUp(self):
        super().setUp()
        eng.reset_telegram_alert_state()
        self.addCleanup(eng.reset_telegram_alert_state)

    def test_push_failure_does_not_affect_telegram(self):
        ps.register_push_token(1, TOKEN_A, "android")

        def broken_sender(token, title, body, data):
            raise ps.PushSendError("provider down")

        push_result = ps.send_push_notification(1, "t", "b", sender=broken_sender)
        self.assertEqual(push_result["sent"], 0)

        with patch.object(eng, "_send_alert_transport", lambda message: "sent"):
            telegram_result = eng._dispatch_prepared_alert(
                {"ticker": "PETR4"},
                {"alert_level": eng.ALERT_HIGH, "fingerprint": "FP-ISO-1"},
                now=1000.0,
                cooldown_seconds=60,
            )
        self.assertEqual(telegram_result["status"], "sent")

    def test_telegram_failure_does_not_affect_push(self):
        with patch.object(eng, "_send_alert_transport", lambda message: "failed"):
            telegram_result = eng._dispatch_prepared_alert(
                {"ticker": "PETR4"},
                {"alert_level": eng.ALERT_HIGH, "fingerprint": "FP-ISO-2"},
                now=1000.0,
                cooldown_seconds=60,
            )
        self.assertEqual(telegram_result["status"], "error")

        ps.register_push_token(1, TOKEN_A, "android")
        push_result = ps.send_push_notification(1, "t", "b", sender=lambda *a: None)
        self.assertEqual(push_result["sent"], 1)

    def test_push_kill_switch_does_not_block_telegram(self):
        os.environ["DISABLE_PUSH_ALERTS"] = "1"
        self.assertIsNotNone(ks.alert_channel_block_reason("push"))
        self.assertIsNone(ks.alert_channel_block_reason("telegram"))

    def test_telegram_kill_switch_does_not_block_push(self):
        os.environ["DISABLE_TELEGRAM_ALERTS"] = "1"
        self.assertIsNotNone(ks.alert_channel_block_reason("telegram"))
        self.assertIsNone(ks.alert_channel_block_reason("push"))


# =====================================================
# MULTIPROCESSO E DOCUMENTAÇÃO (32-19, 32-14)
# =====================================================

class MultiprocessRiskTests(unittest.TestCase):
    def test_api_runs_single_process_per_instance(self):
        render = (REPO_ROOT / "render.yaml").read_text(encoding="utf-8")
        api_line = next(line for line in render.splitlines() if "uvicorn main:app" in line)
        self.assertNotIn("--workers", api_line)

    def test_alert_dispatch_is_worker_owned(self):
        # dispatch de Push/Telegram acontece somente no serviço worker
        # (processo único), o que mantém o dedup em memória coerente na
        # topologia atual. Escala horizontal exige decisão de negócio.
        render = (REPO_ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("python worker.py", render)
        main_source = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("dispatch_signal_pushes", main_source)
        self.assertNotIn("send_bulk_alert", main_source)

    def test_mission_documentation_records_formal_classifications(self):
        doc = (REPO_ROOT / "docs/mission_32_push_telegram_alerts.md").read_text(encoding="utf-8")
        self.assertIn("BUSINESS_DECISION_REQUIRED", doc)
        self.assertIn("multiprocess", doc.lower())
        self.assertIn("DISABLE_PUSH_ALERTS", doc)
        self.assertIn("DISABLE_TELEGRAM_ALERTS", doc)
        self.assertIn("READ_ONLY_MODE", doc)
        self.assertIn("PAPER_ONLY", doc)


class PaperOnlyIntegrityTests(_EnvCleanMixin):
    def test_paper_only_mode_preserved(self):
        self.assertEqual(PAPER_TRADING_MODE, "PAPER_ONLY")
        self.assertEqual(ks.get_kill_switch_status()["PAPER_ONLY"], "PAPER_ONLY")

    def test_kill_switches_never_flip_paper_only(self):
        os.environ["READ_ONLY_MODE"] = "1"
        os.environ["DISABLE_AI_DECISIONS"] = "1"
        self.assertEqual(ks.get_kill_switch_status()["PAPER_ONLY"], "PAPER_ONLY")


if __name__ == "__main__":
    unittest.main()
