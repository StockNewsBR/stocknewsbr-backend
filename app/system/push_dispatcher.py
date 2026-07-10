import json
import math
import os
import threading
import time
from pathlib import Path

from app.database import SessionLocal
from app.models import User
from app.services.push_service import get_push_token_store, send_push_notification
from app.services.score_display import attach_master_score_display_contract
from app.services.snapshot_contract import build_decision_envelope, is_actionable_snapshot_row
from app.services.symbol_registry import canonical_symbol
from app.system.kill_switches import alert_channel_block_reason, symbol_block_reason
from app.system.observability_engine import record_observability_event


PUSH_DISPATCH_STATE_PATH = Path("data/push_dispatch_state.json")


def _score_threshold_from_env(value, default: float = 8.5) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if not math.isfinite(parsed) or parsed <= 0:
        parsed = default
    if parsed > 10.0:
        if 50.0 <= parsed <= 100.0:
            return parsed / 10.0
        return default
    return parsed


def _positive_int_from_env(name: str, default: int, minimum: int) -> int:
    try:
        parsed = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


_PUSH_SCORE_THRESHOLD_ENV = os.getenv("PUSH_SIGNAL_SCORE_THRESHOLD", "8.5")
PUSH_SCORE_THRESHOLD = _score_threshold_from_env(_PUSH_SCORE_THRESHOLD_ENV)
PUSH_MAX_SIGNALS_PER_CYCLE = _positive_int_from_env("PUSH_MAX_SIGNALS_PER_CYCLE", 2, 1)
PUSH_SIGNAL_COOLDOWN_SECONDS = _positive_int_from_env("PUSH_SIGNAL_COOLDOWN_SECONDS", 1800, 300)
_lock = threading.RLock()


def _load_state():
    with _lock:
        if not PUSH_DISPATCH_STATE_PATH.exists():
            return {}

        try:
            return json.loads(PUSH_DISPATCH_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}


def _scale_hint(source, *keys):
    if not isinstance(source, dict):
        return ""
    for key in keys:
        value = str(source.get(key) or "").strip()
        if value in {"0_10", "0_100"}:
            return value
    return ""


def _raw_master_score_payload(signal, display_contract=None):
    def _finite_raw(value):
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, str) and not value.strip():
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(parsed) else None

    def _valid_for_scale(value, scale):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(parsed) or parsed < 0:
            return False
        if scale == "0_10":
            return parsed <= 10.0
        if scale == "0_100":
            return parsed <= 100.0
        return False

    def _infer_raw_scale(value):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return ""
        if not math.isfinite(parsed) or parsed < 0:
            return ""
        if 10.0 < parsed <= 100.0:
            return "0_100"
        return ""

    if isinstance(display_contract, dict):
        contract_raw = display_contract.get("master_score_raw")
        finite_contract_raw = _finite_raw(contract_raw)
        if finite_contract_raw is not None:
            if _valid_for_scale(finite_contract_raw, "0_100"):
                return finite_contract_raw, "0_100"
    raw_score = signal.get("master_score_raw") if isinstance(signal, dict) else None
    finite_raw_score = _finite_raw(raw_score)
    if finite_raw_score is not None:
        if _valid_for_scale(finite_raw_score, "0_100"):
            return finite_raw_score, "0_100"
    if not isinstance(signal, dict):
        return "", ""
    for key in ("master_score", "score"):
        legacy_score = signal.get(key)
        if _finite_raw(legacy_score) is None:
            continue
        if key == "score":
            explicit_scale = _scale_hint(signal, "score_source_scale", "source_scale")
        else:
            explicit_scale = _scale_hint(signal, "master_score_source_scale", "master_score_scale", "source_scale")
        if explicit_scale:
            if explicit_scale == "0_100" and _valid_for_scale(legacy_score, explicit_scale):
                return legacy_score, explicit_scale
            if explicit_scale == "0_10" and _valid_for_scale(legacy_score, explicit_scale):
                return round(float(legacy_score) * 10.0, 1), "0_100"
            continue
        try:
            parsed_legacy_score = float(legacy_score)
            if math.isfinite(parsed_legacy_score) and 10.0 < parsed_legacy_score <= 100.0:
                return legacy_score, "0_100"
        except (TypeError, ValueError):
            continue
    return "", ""


def _raw_master_score_source(signal, display_contract=None):
    return _raw_master_score_payload(signal, display_contract)[1]


def _save_state(state):
    with _lock:
        PUSH_DISPATCH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PUSH_DISPATCH_STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )


def _eligible_signals(signals):
    ranked = []

    for item in signals or []:
        if not isinstance(item, dict):
            continue

        if not is_actionable_snapshot_row(item):
            continue

        display_contract = attach_master_score_display_contract(item)
        try:
            score = float(display_contract.get("master_score", 0.0) or 0.0)
        except Exception:
            score = 0.0

        if score < PUSH_SCORE_THRESHOLD:
            continue

        ticker = canonical_symbol(item.get("canonical_symbol") or item.get("ticker") or item.get("symbol"))

        if not ticker:
            continue

        ranked.append((score, item))

    ranked.sort(key=lambda row: row[0], reverse=True)
    return [item for _, item in ranked[:PUSH_MAX_SIGNALS_PER_CYCLE]]


def dispatch_signal_pushes(signals):
    # Mission 32: kill switch operacional bloqueia o canal inteiro de forma
    # auditável antes de qualquer acesso a tokens ou estado.
    kill_reason = alert_channel_block_reason("push")
    if kill_reason:
        record_observability_event(
            "push",
            "push_dispatch_blocked_by_kill_switch",
            severity="warning",
            source="push_dispatcher",
            details={"reason": kill_reason, "signals": len(signals or [])},
        )
        return {"sent": 0, "signals": 0, "blocked_by": kill_reason}

    candidates = _eligible_signals(signals)

    if not candidates:
        return {"sent": 0, "signals": 0}

    now = int(time.time())
    state = _load_state()
    token_store = get_push_token_store()
    token_user_ids = []

    for key, tokens in token_store.items():
        if not tokens:
            continue
        try:
            token_user_ids.append(int(key))
        except Exception:
            continue

    token_user_ids = sorted(set(token_user_ids))

    if not token_user_ids:
        return {"sent": 0, "signals": len(candidates)}

    dispatched = 0
    db = SessionLocal()

    try:
        users = (
            db.query(User)
            .filter(User.is_active == True, User.access_app == True)  # noqa: E712
            .filter(User.id.in_(token_user_ids))
            .all()
        )

        for signal in candidates:
            ticker = canonical_symbol(signal.get("canonical_symbol") or signal.get("ticker") or signal.get("symbol"))

            # Mission 32: símbolo desativado por kill switch — pulo auditável.
            symbol_reason = symbol_block_reason(ticker)
            if symbol_reason:
                record_observability_event(
                    "push",
                    "push_signal_blocked_by_symbol_kill_switch",
                    severity="warning",
                    source="push_dispatcher",
                    details={"ticker": ticker, "reason": symbol_reason},
                )
                continue

            decision_envelope = build_decision_envelope(signal)
            last_sent = int(state.get(ticker, 0) or 0)

            if now - last_sent < PUSH_SIGNAL_COOLDOWN_SECONDS:
                # Mission 32: cooldown é rate limit intencional, mas o pulo
                # precisa ser auditável (nenhum alerta perdido em silêncio).
                record_observability_event(
                    "push",
                    "push_signal_skipped_cooldown",
                    severity="info",
                    source="push_dispatcher",
                    details={"ticker": ticker, "cooldown_remaining_seconds": int(PUSH_SIGNAL_COOLDOWN_SECONDS - (now - last_sent))},
                )
                continue

            title = f"Alerta SNBR: {ticker}"
            display_contract = attach_master_score_display_contract(signal)
            display_score = display_contract.get("master_score", 0.0)
            raw_master_score, raw_master_score_scale = _raw_master_score_payload(signal, display_contract)
            body = f"Score Mestre {display_score} | {signal.get('master_direction') or signal.get('trend') or 'n/a'}"

            signal_sent = 0

            for user in users:
                tokens = token_store.get(str(user.id), [])
                if not tokens:
                    continue

                result = send_push_notification(
                    user_id=user.id,
                    title=title,
                    body=body,
                    data={
                        "ticker": ticker,
                        "canonical_symbol": ticker,
                        "score": str(display_score),
                        "master_score": str(display_contract.get("master_score", "")),
                        "master_score_raw": str(raw_master_score if raw_master_score not in (None, "") else ""),
                        "master_score_raw_source_scale": str(raw_master_score_scale if raw_master_score_scale else ""),
                        "master_score_source_scale": str(display_contract.get("master_score_source_scale", "")),
                        "master_direction": str(signal.get("master_direction", "")),
                        "master_conviction": str(signal.get("master_conviction", "")),
                        "master_confidence": str(signal.get("master_confidence", "")),
                        "master_risk": str(signal.get("master_risk", "")),
                        "master_status": str(signal.get("master_status", "")),
                        "master_summary": str(signal.get("master_summary", "")),
                        "trend": str(signal.get("trend", "")),
                        "price": str(signal.get("price", "")),
                        "volume": str(signal.get("volume", "")),
                        "data_quality": str(signal.get("data_quality", "")),
                        "decision_status": str(decision_envelope.get("decision_status", "")),
                        "decision_envelope": json.dumps(decision_envelope, ensure_ascii=True, default=str),
                        "decision_state": str(signal.get("decision_state", "")),
                        "trade_action": str(signal.get("trade_action") or signal.get("signal") or ""),
                        "audit_status": str(signal.get("audit_status", "")),
                        "audit_score": str(signal.get("audit_score", "")),
                        "blocked_by_auditor": str(bool(signal.get("blocked_by_auditor") is True)).lower(),
                        "market_data_updated_at": str(signal.get("market_data_updated_at", "")),
                        "snapshot_id": str(signal.get("snapshot_id", "")),
                    },
                    tokens=tokens,
                )
                signal_sent += int(result.get("sent", 0) or 0)

            if signal_sent > 0:
                state[ticker] = now
                dispatched += signal_sent
                record_observability_event(
                    "push",
                    "push_signal_dispatched",
                    severity="info",
                    source="push_dispatcher",
                    details={"ticker": ticker, "sent": signal_sent},
                )

        _save_state(state)
        return {"sent": dispatched, "signals": len(candidates)}
    finally:
        db.close()
