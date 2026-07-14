# =====================================================
# STOCKNEWSBR TELEGRAM ALERT ENGINE
# =====================================================

import time
import logging
import threading
import requests
from collections import deque
from typing import Any

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.ai.final_decision import FINAL_CONFIRMED, FINAL_FORMING, FINAL_NO_TRADE
from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED
from app.ai.institutional_conviction import CONVICTION_HIGH, CONVICTION_MODERATE, CONVICTION_VERY_HIGH
from app.ai.institutional_priority import PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_MEDIUM
from app.ai.operational_rules import OPERATIONAL_BLOCKED, OPERATIONAL_READY
from app.core.settings import settings
from app.services.score_display import attach_master_score_display_contract
from app.services.snapshot_contract import DECISION_READY, audit_status_value, build_decision_envelope
from app.services.symbol_registry import canonical_symbol
from app.system.kill_switches import alert_channel_block_reason, symbol_block_reason
from app.system.observability_engine import record_observability_event
from app.system.system_metrics import get_telegram_alert_metrics_snapshot, record_telegram_alert_metric
from app.telegram.telegram_alert_formatter import format_signal_alert

logger = logging.getLogger("stocknewsbr.telegram")

# =====================================================
# CONFIG
# =====================================================

TELEGRAM_TOKEN = settings.TELEGRAM_TOKEN
CHAT_ID = settings.TELEGRAM_CHAT_ID

BASE_URL = "https://api.telegram.org/bot"

TIMEOUT = (3, 6)

MIN_ALERT_INTERVAL = 1

TELEGRAM_ALERT_COOLDOWN_SECONDS = max(60, int(getattr(settings, "TELEGRAM_ALERT_COOLDOWN_SECONDS", 1800) or 1800))
MAX_ALERTS_PER_BATCH = max(1, int(getattr(settings, "TELEGRAM_MAX_ALERTS_PER_BATCH", 5) or 5))
MAX_ALERT_HISTORY = 100

ALERT_CRITICAL = "critical"
ALERT_HIGH = "high"
ALERT_MEDIUM = "medium"

ALERT_LABELS = {
    ALERT_CRITICAL: "🚨 ALERTA CRÍTICO",
    ALERT_HIGH: "🔥 ALERTA ALTO",
    ALERT_MEDIUM: "🟡 ALERTA MÉDIO",
}

ALERT_ORDER = {
    ALERT_CRITICAL: 0,
    ALERT_HIGH: 1,
    ALERT_MEDIUM: 2,
}

# =====================================================
# STATE
# =====================================================

_last_alert_time = 0.0

_lock = threading.RLock()

_sent_fingerprints: dict[str, float] = {}
_cooldown_until: dict[str, float] = {}
_alert_history: deque[dict[str, Any]] = deque(maxlen=MAX_ALERT_HISTORY)

# =====================================================
# HTTP SESSION
# =====================================================

_session = requests.Session()

# Mission 32: retries limitados com backoff exponencial; jitter quando o
# urllib3 instalado suportar (>=2.0). HTTP 400 fica fora do forcelist de
# propósito: payload inválido é erro permanente e não deve ser re-tentado.
_RETRY_KWARGS = dict(
    total=3,
    backoff_factor=0.5,
    status_forcelist=[429],
    allowed_methods=["POST"],
)

try:
    retry = Retry(backoff_jitter=0.3, **_RETRY_KWARGS)
except TypeError:  # pragma: no cover - urllib3 < 2.0 sem jitter
    retry = Retry(**_RETRY_KWARGS)

adapter = HTTPAdapter(
    pool_connections=10,
    pool_maxsize=10,
    max_retries=retry
)

_session.mount("https://", adapter)
_session.mount("http://", adapter)

# =====================================================
# SEND MESSAGE
# =====================================================

def _plain(value: Any) -> str:
    text = str(value or "").strip()
    for marker in ("🚨", "🔥", "🟡", "🟢", "🔴", "⚪"):
        text = text.replace(marker, "")
    return " ".join(text.upper().split())


def _matches(value: Any, expected: Any) -> bool:
    return _plain(value) == _plain(expected)


def _contains(value: Any, expected: str) -> bool:
    return _plain(expected) in _plain(value)


def _ticker(signal: dict[str, Any]) -> str:
    return canonical_symbol(signal.get("canonical_symbol") or signal.get("ticker") or signal.get("symbol"))


def _direction(signal: dict[str, Any]) -> str:
    return str(
        signal.get("master_direction")
        or signal.get("trade_direction")
        or signal.get("trade_action")
        or signal.get("signal")
        or ""
    ).upper().strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _display_score_value(signal: dict[str, Any]) -> float:
    display_contract = attach_master_score_display_contract(signal if isinstance(signal, dict) else {})
    return _safe_float(display_contract.get("master_score"), 0.0)


def _alert_priority_score_value(signal: dict[str, Any]) -> float:
    if not isinstance(signal, dict):
        return 0.0
    display_contract = attach_master_score_display_contract(signal)
    source_scale = str(display_contract.get("master_score_source_scale") or "").strip()
    raw_score = display_contract.get("master_score_raw")
    try:
        if isinstance(raw_score, bool):
            raise TypeError
        numeric = float(raw_score)
        if source_scale == "0_100" and 0.0 <= numeric <= 100.0:
            return numeric
    except (TypeError, ValueError):
        pass
    return _safe_float(display_contract.get("master_score"), 0.0) * 10.0


def _event_payload(
    *,
    signal: dict[str, Any] | None,
    status: str,
    reason: str,
    alert_level: str | None = None,
    fingerprint: str | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    safe_signal = signal if isinstance(signal, dict) else {}
    ticker = _ticker(safe_signal)
    display_contract = attach_master_score_display_contract(safe_signal)
    raw_master_score = display_contract.get("master_score_raw")
    return {
        "timestamp": time.time(),
        "status": status,
        "ticker": ticker,
        "canonical_symbol": ticker,
        "direction": _direction(safe_signal),
        "final_decision": safe_signal.get("final_decision"),
        "decision_status": (safe_signal.get("decision_envelope") if isinstance(safe_signal.get("decision_envelope"), dict) else {}).get("decision_status") or safe_signal.get("decision_status"),
        "priority_level": safe_signal.get("priority_level"),
        "conviction_level": safe_signal.get("conviction_level"),
        "operational_status": safe_signal.get("operational_status"),
        "audit_status": audit_status_value(safe_signal) if safe_signal else "",
        "alert_level": alert_level,
        "alert_label": ALERT_LABELS.get(str(alert_level or "")),
        "reason": reason,
        "message": message,
        "fingerprint": fingerprint,
        "master_score": display_contract.get("master_score"),
        "master_score_raw": raw_master_score,
        "master_score_source_scale": display_contract.get("master_score_source_scale"),
        "master_score_display_warning": display_contract.get("master_score_display_warning"),
        "final_decision_score": safe_signal.get("final_decision_score"),
        "final_decision_confidence": safe_signal.get("final_decision_confidence"),
    }


def _record_event(event: dict[str, Any], metric: str, alert_level: str | None = None) -> None:
    record_telegram_alert_metric(metric, alert_level=alert_level)
    with _lock:
        _alert_history.appendleft(dict(event))
    record_observability_event(
        "telegram",
        str(event.get("reason") or metric),
        severity="warning" if metric in {"blocked", "discarded", "deduplicated", "cooldown", "errors"} else "info",
        source="telegram_alert_engine",
        details={
            "ticker": event.get("ticker"),
            "status": event.get("status"),
            "alert_level": event.get("alert_level"),
            "final_decision": event.get("final_decision"),
        },
    )


def _prune_state(now: float, cooldown_seconds: int) -> None:
    expired_fingerprints = [
        key
        for key, last_seen in _sent_fingerprints.items()
        if now - float(last_seen or 0.0) > max(60, cooldown_seconds)
    ]
    for key in expired_fingerprints:
        _sent_fingerprints.pop(key, None)

    expired_cooldowns = [
        key
        for key, cooldown_until in _cooldown_until.items()
        if float(cooldown_until or 0.0) <= now
    ]
    for key in expired_cooldowns:
        _cooldown_until.pop(key, None)


def telegram_alert_fingerprint(signal: dict[str, Any]) -> str:
    if not isinstance(signal, dict):
        return ""
    fields = (
        _ticker(signal),
        _direction(signal),
        signal.get("final_decision"),
        signal.get("priority_level"),
        signal.get("conviction_level"),
        signal.get("operational_status"),
        audit_status_value(signal),
        signal.get("final_decision_summary") or signal.get("final_decision_reason"),
    )
    return "|".join(_plain(field) for field in fields if _plain(field))


def _cooldown_key(signal: dict[str, Any], alert_level: str) -> str:
    return "|".join(
        _plain(field)
        for field in (
            _ticker(signal),
            _direction(signal),
            signal.get("final_decision"),
            alert_level,
        )
        if _plain(field)
    )


def _blocking_reason(signal: dict[str, Any]) -> str | None:
    envelope = build_decision_envelope(signal)
    if envelope.get("decision_status") != DECISION_READY or envelope.get("decision_ready") is not True:
        blockers = envelope.get("blockers") if isinstance(envelope.get("blockers"), list) else []
        reason = ";".join(str(item) for item in blockers[:4] if str(item or "").strip())
        return f"decision_envelope={envelope.get('decision_status')}" + (f":{reason}" if reason else "")

    operational_status = str(signal.get("operational_status") or "").upper().strip()
    audit_status = audit_status_value(signal)

    if operational_status == OPERATIONAL_BLOCKED:
        return "operational_status=BLOCKED"
    if audit_status == AUDIT_BLOCKED:
        return "audit_status=BLOCKED"
    if signal.get("decision_ready") is not True:
        return "decision_ready=False"
    if signal.get("radar_no_trade_now") is True:
        return "radar_no_trade_now=True"
    if _matches(signal.get("final_decision"), FINAL_NO_TRADE) or _contains(signal.get("final_decision"), "NÃO OPERAR AGORA"):
        return "final_decision=NÃO OPERAR AGORA"
    return None


def classify_telegram_alert(signal: dict[str, Any]) -> str | None:
    if not isinstance(signal, dict):
        return None

    final_decision = signal.get("final_decision")
    priority_level = signal.get("priority_level")
    conviction_level = signal.get("conviction_level")
    operational_status = str(signal.get("operational_status") or "").upper().strip()
    audit_status = audit_status_value(signal)

    if (
        _matches(final_decision, FINAL_CONFIRMED)
        and _matches(priority_level, PRIORITY_CRITICAL)
        and _matches(conviction_level, CONVICTION_VERY_HIGH)
        and operational_status == OPERATIONAL_READY
        and audit_status == AUDIT_APPROVED
    ):
        return ALERT_CRITICAL

    if (
        _matches(final_decision, FINAL_CONFIRMED)
        and _matches(priority_level, PRIORITY_HIGH)
        and _matches(conviction_level, CONVICTION_HIGH)
    ):
        return ALERT_HIGH

    if (
        _matches(final_decision, FINAL_FORMING)
        and _matches(priority_level, PRIORITY_MEDIUM)
        and _matches(conviction_level, CONVICTION_MODERATE)
    ):
        return ALERT_MEDIUM

    return None


def build_telegram_alert(signal: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(signal, dict):
        return _event_payload(signal=None, status="discarded", reason="invalid_signal")

    ticker = _ticker(signal)
    if not ticker:
        return _event_payload(signal=signal, status="discarded", reason="missing_ticker")

    # Mission 32: kill switches operacionais têm precedência máxima — o
    # bloqueio é explícito, auditável e reversível (rollback = limpar a env).
    kill_reason = alert_channel_block_reason("telegram") or symbol_block_reason(ticker)
    if kill_reason:
        return _event_payload(signal=signal, status="blocked", reason=kill_reason)

    blocked_reason = _blocking_reason(signal)
    if blocked_reason:
        return _event_payload(signal=signal, status="blocked", reason=blocked_reason)

    # Mission 31F: acesso Telegram precisa ter sido validado explicitamente.
    # Dados ausentes não são considerados válidos. Avaliado após os bloqueios
    # de decisão para preservar a precedência de motivo (Mission 29).
    access = signal.get("telegram_access")
    if not isinstance(access, dict) or "allowed" not in access:
        return _event_payload(signal=signal, status="blocked", reason="telegram_access_not_validated")
    if access.get("allowed") is not True:
        return _event_payload(
            signal=signal,
            status="blocked",
            reason=str(access.get("reason") or "telegram_access_required"),
        )

    alert_level = classify_telegram_alert(signal)
    if not alert_level:
        return _event_payload(signal=signal, status="discarded", reason="alert_level_not_institutional")

    fingerprint = telegram_alert_fingerprint(signal)
    return _event_payload(
        signal=signal,
        status="ready",
        reason="contratos finais aprovados para interrupcao do trader",
        alert_level=alert_level,
        fingerprint=fingerprint,
    )


TRANSPORT_SENT = "sent"
TRANSPORT_FAILED = "failed"
TRANSPORT_UNKNOWN = "unknown"


def _scrub_secret(text: Any) -> str:
    # Mission 32: exceções de rede (requests) incluem a URL completa, que
    # contém o bot token. Nunca registrar o token em log.
    value = str(text or "")
    if TELEGRAM_TOKEN:
        value = value.replace(TELEGRAM_TOKEN, "***TELEGRAM_TOKEN***")
    if CHAT_ID:
        value = value.replace(str(CHAT_ID), "***CHAT_ID***")
    return value


def _send_alert_transport(message: str) -> str:
    """Envia a mensagem e devolve TRANSPORT_SENT/FAILED/UNKNOWN.

    UNKNOWN = a requisição pode ter chegado ao provider (ex.: read timeout);
    o chamador NÃO deve re-enviar automaticamente para evitar duplicação.
    """
    global _last_alert_time

    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.warning("Telegram token or chat_id not configured")
        return TRANSPORT_FAILED

    with _lock:
        elapsed = time.time() - _last_alert_time
        if elapsed < MIN_ALERT_INTERVAL:
            time.sleep(MIN_ALERT_INTERVAL - elapsed)
        _last_alert_time = time.time()

    url = f"{BASE_URL}{TELEGRAM_TOKEN}/sendMessage"

    # Mission 32: texto plano (sem parse_mode). O template não usa marcação e
    # conteúdo dinâmico sem escape podia derrubar o envio com HTTP 400
    # (entity parse error) — perda silenciosa de alerta + injeção de Markdown.
    payload = {
        "chat_id": CHAT_ID,
        "text": message[:4000],
    }

    try:
        r = _session.post(url, json=payload, timeout=TIMEOUT)
    except requests.exceptions.ReadTimeout as e:
        # A mensagem pode ter sido aceita pelo provider: resultado ambíguo.
        logger.error("Telegram send timeout (ambiguous): %s", _scrub_secret(e))
        return TRANSPORT_UNKNOWN
    except Exception as e:
        logger.error("Telegram send error: %s", _scrub_secret(e))
        return TRANSPORT_FAILED

    if r.status_code != 200:
        logger.warning("Telegram status %s", r.status_code)
        return TRANSPORT_FAILED

    return TRANSPORT_SENT


def send_alert(message: str):
    """Seam público/histórico de envio usado pelo dispatch e por testes.

    Retorna o status tri-state do transporte. Valores booleanos (mocks
    legados) são aceitos pelo dispatch via _coerce_transport_status.
    """
    return _send_alert_transport(message)


def _coerce_transport_status(value) -> str:
    if value in (TRANSPORT_SENT, TRANSPORT_FAILED, TRANSPORT_UNKNOWN):
        return value
    # Compatibilidade com a interface booleana histórica (True/False).
    return TRANSPORT_SENT if value else TRANSPORT_FAILED

# =====================================================
# SIGNAL ALERT
# =====================================================

def _dispatch_prepared_alert(
    signal: dict[str, Any],
    prepared: dict[str, Any],
    *,
    regime=None,
    now: float | None = None,
    cooldown_seconds: int | None = None,
) -> dict[str, Any]:
    current_time = float(now if now is not None else time.time())
    cooldown = max(60, int(cooldown_seconds or TELEGRAM_ALERT_COOLDOWN_SECONDS))
    alert_level = str(prepared.get("alert_level") or "")
    fingerprint = str(prepared.get("fingerprint") or telegram_alert_fingerprint(signal))
    equivalent_key = _cooldown_key(signal, alert_level)

    with _lock:
        _prune_state(current_time, cooldown)
        last_fingerprint = _sent_fingerprints.get(fingerprint)
        if last_fingerprint and current_time - float(last_fingerprint or 0.0) < cooldown:
            event = _event_payload(
                signal=signal,
                status="deduplicated",
                reason="telegram_alert_fingerprint repetido em curto periodo",
                alert_level=alert_level,
                fingerprint=fingerprint,
            )
            _record_event(event, "deduplicated", alert_level=alert_level)
            return event

        cooldown_until = float(_cooldown_until.get(equivalent_key) or 0.0)
        if cooldown_until > current_time:
            event = _event_payload(
                signal=signal,
                status="cooldown",
                reason="alerta equivalente em cooldown",
                alert_level=alert_level,
                fingerprint=fingerprint,
            )
            event["cooldown_remaining_seconds"] = int(cooldown_until - current_time)
            _record_event(event, "cooldown", alert_level=alert_level)
            return event

        # Mission 31F: reserva o fingerprint antes de liberar o lock para que
        # envios concorrentes do mesmo alerta sejam deduplicados de forma
        # determinística (apenas um envia).
        _sent_fingerprints[fingerprint] = current_time

    message = f"{ALERT_LABELS.get(alert_level, 'ALERTA')}\n\n{format_signal_alert(signal, regime)}"
    transport_status = _coerce_transport_status(send_alert(message))

    if transport_status == TRANSPORT_SENT:
        with _lock:
            _sent_fingerprints[fingerprint] = current_time
            _cooldown_until[equivalent_key] = current_time + cooldown
        event = _event_payload(
            signal=signal,
            status="sent",
            reason="contratos finais justificam alerta institucional",
            alert_level=alert_level,
            fingerprint=fingerprint,
            message=message[:400],
        )
        _record_event(event, "sent", alert_level=alert_level)
        return event

    if transport_status == TRANSPORT_UNKNOWN:
        # Mission 32: timeout ambíguo — a mensagem pode ter sido entregue.
        # Mantém a reserva do fingerprint (sem re-envio automático que
        # duplicaria o alerta) e registra o resultado como UNKNOWN, nunca
        # como DELIVERED. O evento auditável impede perda silenciosa.
        event = _event_payload(
            signal=signal,
            status="unknown",
            reason="telegram_send_timeout_ambiguous",
            alert_level=alert_level,
            fingerprint=fingerprint,
        )
        _record_event(event, "errors", alert_level=alert_level)
        return event

    with _lock:
        # Falha definitiva no envio: libera a reserva para não mascarar
        # futuros alertas (retry legítimo em ciclo seguinte).
        if _sent_fingerprints.get(fingerprint) == current_time:
            _sent_fingerprints.pop(fingerprint, None)

    event = _event_payload(
        signal=signal,
        status="error",
        reason="telegram_send_failed",
        alert_level=alert_level,
        fingerprint=fingerprint,
    )
    _record_event(event, "errors", alert_level=alert_level)
    return event


def send_signal_alert(signal: dict, regime=None, *, now: float | None = None, cooldown_seconds: int | None = None):

    try:

        prepared = build_telegram_alert(signal)
        status = prepared.get("status")

        if status == "blocked":
            _record_event(prepared, "blocked")
            return prepared

        if status == "discarded":
            _record_event(prepared, "discarded")
            return prepared

        return _dispatch_prepared_alert(
            signal,
            prepared,
            regime=regime,
            now=now,
            cooldown_seconds=cooldown_seconds,
        )

    except Exception as e:

        logger.error(f"Signal alert error: {e}")
        event = _event_payload(signal=signal if isinstance(signal, dict) else None, status="error", reason=str(e)[:160])
        _record_event(event, "errors")
        return event

# =====================================================
# BULK ALERT
# =====================================================

def send_bulk_alert(signals, regime=None, *, now: float | None = None, cooldown_seconds: int | None = None, max_alerts: int | None = None):

    if not signals:
        return {"sent": 0, "blocked": 0, "discarded": 0, "deduplicated": 0, "cooldown": 0, "errors": 0, "items": []}

    try:
        prepared_alerts: list[tuple[dict[str, Any], dict[str, Any]]] = []
        results: list[dict[str, Any]] = []

        for signal in signals:
            prepared = build_telegram_alert(signal)
            status = prepared.get("status")

            if status == "ready":
                prepared_alerts.append((signal, prepared))
                continue

            metric = "blocked" if status == "blocked" else "discarded"
            _record_event(prepared, metric)
            results.append(prepared)

        prepared_alerts.sort(
            key=lambda item: (
                ALERT_ORDER.get(str(item[1].get("alert_level") or ""), 99),
                -_safe_float(item[0].get("final_decision_score")),
                -_alert_priority_score_value(item[0]),
            )
        )

        safe_limit = max(1, int(max_alerts or MAX_ALERTS_PER_BATCH))
        selected = prepared_alerts[:safe_limit]
        overflow = prepared_alerts[safe_limit:]

        for signal, prepared in overflow:
            event = _event_payload(
                signal=signal,
                status="discarded",
                reason="batch_limit_anti_spam",
                alert_level=str(prepared.get("alert_level") or ""),
                fingerprint=str(prepared.get("fingerprint") or ""),
            )
            _record_event(event, "discarded", alert_level=str(prepared.get("alert_level") or ""))
            results.append(event)

        for signal, prepared in selected:
            results.append(
                _dispatch_prepared_alert(
                    signal,
                    prepared,
                    regime=regime,
                    now=now,
                    cooldown_seconds=cooldown_seconds,
                )
            )

        summary = {key: 0 for key in ("sent", "blocked", "discarded", "deduplicated", "cooldown", "errors")}
        for item in results:
            status = str(item.get("status") or "")
            if status in summary:
                summary[status] += 1
            elif status in {"error", "unknown"}:
                summary["errors"] += 1
        summary["items"] = results
        return summary

    except Exception as e:

        logger.error(f"Bulk alert error: {e}")
        event = _event_payload(signal=None, status="error", reason=str(e)[:160])
        _record_event(event, "errors")
        return {"sent": 0, "blocked": 0, "discarded": 0, "deduplicated": 0, "cooldown": 0, "errors": 1, "items": [event]}


def get_telegram_alert_history(limit: int = 20) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 20), MAX_ALERT_HISTORY))
    with _lock:
        return [dict(item) for item in list(_alert_history)[:safe_limit]]


def get_telegram_health() -> dict[str, Any]:
    metrics = get_telegram_alert_metrics_snapshot()
    activity = sum(int(metrics.get(key, 0) or 0) for key in ("sent", "blocked", "discarded", "deduplicated", "cooldown"))
    status = "IDLE"
    if int(metrics.get("errors", 0) or 0) > 0:
        status = "DEGRADED"
    elif activity > 0:
        status = "HEALTHY"
    return {
        "status": status,
        "sent": int(metrics.get("sent", 0) or 0),
        "blocked": int(metrics.get("blocked", 0) or 0),
        "discarded": int(metrics.get("discarded", 0) or 0),
        "deduplicated": int(metrics.get("deduplicated", 0) or 0),
        "cooldown": int(metrics.get("cooldown", 0) or 0),
        "errors": int(metrics.get("errors", 0) or 0),
        "critical": int(metrics.get("critical", 0) or 0),
        "high": int(metrics.get("high", 0) or 0),
        "medium": int(metrics.get("medium", 0) or 0),
        "cooldown_seconds": TELEGRAM_ALERT_COOLDOWN_SECONDS,
        "kill_switches": {
            "telegram_alerts_disabled": alert_channel_block_reason("telegram") is not None,
            "block_reason": alert_channel_block_reason("telegram"),
        },
        "last_alerts": get_telegram_alert_history(limit=10),
        "updated_at": metrics.get("updated_at", 0.0),
    }


def reset_telegram_alert_state() -> None:
    with _lock:
        _sent_fingerprints.clear()
        _cooldown_until.clear()
        _alert_history.clear()
