from __future__ import annotations

from typing import Any, Iterable


ACTIONABLE_SIGNALS = {"BUY", "SELL", "SHORT", "COVER"}
READY_DECISION_STATES = {"BUY_READY", "SELL_READY", "SHORT_READY"}
BLOCKED_DECISION_STATES = {"WATCH", "WAIT", "NO_TRADE", "DO_NOT_TRADE"}
READY_STATE_BY_SIGNAL = {
    "BUY": "BUY_READY",
    "SHORT": "SHORT_READY",
    "SELL": "SELL_READY",
    "COVER": "SELL_READY",
}
BLOCKED_DATA_QUALITIES = {
    "score_only",
    "score only",
    "missing",
    "empty",
    "stale",
    "no_price",
    "no-price",
    "no price",
    "provider_failed",
    "provider-failed",
    "provider failed",
    "failed",
    "error",
    "timeout",
    "unavailable",
    "invalid",
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def snapshot_signal_value(row: dict[str, Any]) -> str:
    return str(row.get("trade_action") or row.get("signal") or row.get("action") or "").upper().strip()


def snapshot_decision_state(row: dict[str, Any]) -> str:
    return str(row.get("decision_state") or "").upper().strip()


def has_positive_value(row: dict[str, Any], *keys: str) -> bool:
    return any(safe_float(row.get(key)) > 0 for key in keys)


def has_blocking_reasons(row: dict[str, Any]) -> bool:
    reasons = row.get("blocked_reasons") or row.get("warnings") or []
    if isinstance(reasons, str):
        return bool(reasons.strip())
    if isinstance(reasons, (list, tuple, set)):
        return any(str(item).strip() for item in reasons)
    return bool(reasons)


def is_actionable_snapshot_row(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    signal = snapshot_signal_value(row)
    if signal not in ACTIONABLE_SIGNALS:
        return False
    if row.get("decision_ready") is not True:
        return False
    decision_state = snapshot_decision_state(row)
    if decision_state:
        if decision_state in BLOCKED_DECISION_STATES:
            return False
        if decision_state not in READY_DECISION_STATES:
            return False
        if decision_state != READY_STATE_BY_SIGNAL.get(signal):
            return False
    if row.get("stale") is True or row.get("is_stale") is True:
        return False
    if str(row.get("data_quality") or "").lower().strip() in BLOCKED_DATA_QUALITIES:
        return False
    for status_key in ("quote_status", "status", "provider_status", "market_data_status"):
        if str(row.get(status_key) or "").lower().strip() in BLOCKED_DATA_QUALITIES:
            return False
    if row.get("provider_failed") is True or row.get("provider_error") is True:
        return False
    if has_blocking_reasons(row):
        return False
    if not has_positive_value(row, "price", "close", "last_price"):
        return False
    if not has_positive_value(row, "volume", "last_volume"):
        return False
    return True


def actionable_snapshot_rows(rows: Iterable[Any], limit: int | None = None) -> list[dict[str, Any]]:
    output = [dict(row) for row in rows or [] if is_actionable_snapshot_row(row)]
    return output[:limit] if limit is not None else output


def normalize_snapshot_events(events: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if not isinstance(events, (list, tuple)):
        return normalized
    for event in events:
        if isinstance(event, dict):
            normalized.append(dict(event))
            continue
        label = str(event or "").strip()
        if label:
            normalized.append({"type": label, "label": label})
    return normalized


def snapshot_surface_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    output = dict(row)
    ticker = output.get("ticker") or output.get("symbol")
    if ticker:
        output["ticker"] = ticker
        output["symbol"] = ticker
    output["events"] = normalize_snapshot_events(output.get("events"))
    return output
