from __future__ import annotations

from typing import Any, Iterable

from app.services.score_display import attach_master_score_display_contract


ACTIONABLE_SIGNALS = {"BUY", "SELL", "SHORT", "COVER"}
BULLISH_ACTIONS = {"BUY", "COVER"}
BEARISH_ACTIONS = {"SELL", "SHORT"}
BULLISH_WATCH_SIGNALS = {"WATCH_BUY", "WATCH_LONG", "LONG_WATCH"}
BEARISH_WATCH_SIGNALS = {"WATCH_SHORT", "WATCH_SELL", "SHORT_WATCH"}
WATCH_SIGNALS = {"WATCH", "WAIT", "HOLD"} | BULLISH_WATCH_SIGNALS | BEARISH_WATCH_SIGNALS
NO_TRADE_SIGNALS = {"NO_TRADE", "DO_NOT_TRADE"}
MASTER_DIRECTIONS = {"BULLISH", "BEARISH", "NEUTRAL"}
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

QUALITY_REAL_TIME = "real_time"
QUALITY_CACHED = "cached"
QUALITY_STALE = "stale"
QUALITY_EMPTY = "empty"
QUALITY_INVALID = "invalid"
QUALITY_SCORE_ONLY = "score_only"
QUALITY_LABELS = {
    QUALITY_REAL_TIME: "Dados Confiáveis",
    QUALITY_CACHED: "Dados Confiáveis",
    QUALITY_STALE: "Dados Limitados",
    QUALITY_EMPTY: "Dados Limitados",
    QUALITY_INVALID: "Dados Limitados",
    QUALITY_SCORE_ONLY: "Dados Parciais",
}


def coerce_data_quality(row: Any) -> str:
    if not isinstance(row, dict):
        return QUALITY_INVALID

    raw = str(
        row.get("data_quality")
        or row.get("quote_status")
        or row.get("status")
        or row.get("provider_status")
        or row.get("market_data_status")
        or ""
    ).strip().lower()

    if raw in {QUALITY_REAL_TIME, QUALITY_CACHED, QUALITY_STALE, QUALITY_EMPTY, QUALITY_INVALID, QUALITY_SCORE_ONLY}:
        return raw

    if row.get("provider_error") or row.get("provider_failed"):
        return QUALITY_INVALID
    if row.get("stale") is True or row.get("is_stale") is True:
        return QUALITY_STALE
    if raw in {"priced", "valid", "fresh", "ok", "real", "market_cache", "snapshot"}:
        return QUALITY_CACHED if row.get("source") in {"cached", "snapshot", "cache", "market_cache"} else QUALITY_REAL_TIME
    if raw in {"partial", "limited"}:
        return QUALITY_SCORE_ONLY
    if raw in {"missing", "empty", "no_price", "no-price", "no price", "unavailable"}:
        return QUALITY_EMPTY
    if raw in {"invalid", "error", "failed", "timeout", "provider_failed", "provider-failed", "provider failed"}:
        return QUALITY_INVALID
    if raw == "score_only" or raw == "score only":
        return QUALITY_SCORE_ONLY

    price_ok = has_positive_value(row, "price", "close", "last_price")
    volume_ok = has_positive_value(row, "volume", "last_volume")
    if price_ok and volume_ok:
        return QUALITY_REAL_TIME if row.get("source") in {"market", "real_time", "realtime"} else QUALITY_CACHED
    if price_ok or volume_ok:
        return QUALITY_SCORE_ONLY
    return QUALITY_EMPTY


def data_quality_label(quality: str) -> str:
    return QUALITY_LABELS.get(str(quality or "").strip().lower(), "Dados Limitados")


def data_quality_score(quality: str) -> int:
    normalized = str(quality or "").strip().lower()
    return {
        QUALITY_REAL_TIME: 100,
        QUALITY_CACHED: 88,
        QUALITY_SCORE_ONLY: 52,
        QUALITY_STALE: 35,
        QUALITY_EMPTY: 12,
        QUALITY_INVALID: 0,
    }.get(normalized, 0)


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


def snapshot_row_orientation(row: Any) -> str | None:
    if not isinstance(row, dict):
        return None

    master_direction = str(row.get("master_direction") or "").upper().strip()
    if master_direction == "BULLISH":
        return "bullish"
    if master_direction == "BEARISH":
        return "bearish"
    if master_direction == "NEUTRAL":
        return None

    signal = snapshot_signal_value(row)
    if signal in BULLISH_ACTIONS or signal in BULLISH_WATCH_SIGNALS:
        return "bullish"
    if signal in BEARISH_ACTIONS or signal in BEARISH_WATCH_SIGNALS:
        return "bearish"

    for key in ("trade_direction", "trade_bias", "bias", "side", "direction"):
        value = str(row.get(key) or "").strip().lower()
        if value in {"long", "buy", "bull", "bullish", "comprador", "alta"}:
            return "bullish"
        if value in {"short", "sell", "bear", "bearish", "vendedor", "baixa"}:
            return "bearish"

    score = safe_float(row.get("score"), 50.0)
    if score >= 70.0:
        return "bullish"
    if score <= 30.0:
        return "bearish"
    return None


def has_positive_value(row: dict[str, Any], *keys: str) -> bool:
    return any(safe_float(row.get(key)) > 0 for key in keys)


def has_blocking_reasons(row: dict[str, Any]) -> bool:
    reasons = row.get("blocked_reasons") or row.get("warnings") or []
    if isinstance(reasons, str):
        return bool(reasons.strip())
    if isinstance(reasons, (list, tuple, set)):
        return any(str(item).strip() for item in reasons)
    return bool(reasons)


def audit_status_value(row: dict[str, Any]) -> str:
    auditor = row.get("auditor") if isinstance(row.get("auditor"), dict) else {}
    return str(
        row.get("audit_status")
        or row.get("auditor_status")
        or auditor.get("audit_status")
        or auditor.get("auditor_status")
        or ""
    ).upper().strip()


def is_auditor_blocked(row: dict[str, Any]) -> bool:
    auditor = row.get("auditor") if isinstance(row.get("auditor"), dict) else {}
    if row.get("blocked_by_auditor") is True or auditor.get("blocked_by_auditor") is True:
        return True
    if audit_status_value(row) == "BLOCKED":
        return True
    return False


def master_status_value(row: dict[str, Any]) -> str:
    return str(row.get("master_status") or "").upper().strip()


def master_direction_value(row: dict[str, Any]) -> str:
    value = str(row.get("master_direction") or "").upper().strip()
    return value if value in MASTER_DIRECTIONS else ""


def master_confirms_signal(row: dict[str, Any]) -> bool:
    direction = master_direction_value(row)
    if not direction:
        return True
    signal = snapshot_signal_value(row)
    if signal not in ACTIONABLE_SIGNALS:
        return True
    if direction == "BULLISH":
        return signal in BULLISH_ACTIONS
    if direction == "BEARISH":
        return signal in BEARISH_ACTIONS
    return False


def is_actionable_snapshot_row(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    if is_auditor_blocked(row):
        return False
    if master_status_value(row) == "BLOCKED":
        return False
    signal = snapshot_signal_value(row)
    if signal not in ACTIONABLE_SIGNALS:
        return False
    if not master_confirms_signal(row):
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


def is_watchlist_snapshot_row(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    signal = snapshot_signal_value(row)
    decision_state = snapshot_decision_state(row)
    return signal in WATCH_SIGNALS or signal.startswith("WATCH") or decision_state in {"WATCH", "WAIT"}


def is_blocked_snapshot_row(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    if is_actionable_snapshot_row(row):
        return False

    signal = snapshot_signal_value(row)
    decision_state = snapshot_decision_state(row)

    if signal in NO_TRADE_SIGNALS or decision_state in {"NO_TRADE", "DO_NOT_TRADE"}:
        return True
    if is_auditor_blocked(row):
        return True
    if master_status_value(row) == "BLOCKED":
        return True
    if snapshot_signal_value(row) in ACTIONABLE_SIGNALS and not master_confirms_signal(row):
        return True
    if row.get("stale") is True or row.get("is_stale") is True:
        return True
    if str(row.get("data_quality") or "").lower().strip() in BLOCKED_DATA_QUALITIES:
        return True
    for status_key in ("quote_status", "status", "provider_status", "market_data_status"):
        if str(row.get(status_key) or "").lower().strip() in BLOCKED_DATA_QUALITIES:
            return True
    if row.get("provider_failed") is True or row.get("provider_error") is True:
        return True
    if has_blocking_reasons(row):
        return True
    if signal in ACTIONABLE_SIGNALS:
        if row.get("decision_ready") is not True:
            return True
        if not has_positive_value(row, "price", "close", "last_price"):
            return True
        if not has_positive_value(row, "volume", "last_volume"):
            return True
        if decision_state and decision_state != READY_STATE_BY_SIGNAL.get(signal):
            return True
    return False


def snapshot_row_summary(row: dict[str, Any]) -> dict[str, Any]:
    score_display_contract = attach_master_score_display_contract(row)
    return {
        "ticker": row.get("ticker") or row.get("symbol"),
        "symbol": row.get("symbol") or row.get("ticker"),
        "score": row.get("score"),
        "signal": row.get("signal"),
        "trade_action": row.get("trade_action"),
        "decision_ready": row.get("decision_ready"),
        "decision_state": row.get("decision_state"),
        "data_quality": coerce_data_quality(row),
        "blocked_reasons": row.get("blocked_reasons") or [],
        "warnings": row.get("warnings") or [],
        "stale": bool(row.get("stale") is True or row.get("is_stale") is True),
        "provider_error": row.get("provider_error"),
        "price": row.get("price") or row.get("close") or row.get("last_price"),
        "volume": row.get("volume") or row.get("last_volume"),
        "audit_status": row.get("audit_status"),
        "audit_score": row.get("audit_score"),
        "audit_confidence": row.get("audit_confidence"),
        "audit_blocks": row.get("audit_blocks") or [],
        "audit_warnings": row.get("audit_warnings") or [],
        "blocked_by_auditor": bool(row.get("blocked_by_auditor") is True),
        "master_score": score_display_contract.get("master_score"),
        "master_score_raw": score_display_contract.get("master_score_raw"),
        "master_score_display": score_display_contract.get("master_score_display"),
        "master_score_display_warning": score_display_contract.get("master_score_display_warning"),
        "master_direction": row.get("master_direction"),
        "master_conviction": row.get("master_conviction"),
        "master_confidence": row.get("master_confidence"),
        "master_summary": row.get("master_summary"),
        "master_reasoning": row.get("master_reasoning") if isinstance(row.get("master_reasoning"), dict) else {},
        "master_risk": row.get("master_risk"),
        "master_status": row.get("master_status"),
        "opinion_change_conditions": row.get("opinion_change_conditions") or [],
        "strategic_panel": row.get("strategic_panel") if isinstance(row.get("strategic_panel"), dict) else {},
        "strategic_panel_summary": row.get("strategic_panel_summary"),
        "recommended_action": row.get("recommended_action"),
        "historical_confidence_score": row.get("historical_confidence_score"),
        "historical_confidence_label": row.get("historical_confidence_label"),
        "historical_sample_size": row.get("historical_sample_size"),
        "historical_win_rate": row.get("historical_win_rate"),
        "historical_context_match": row.get("historical_context_match"),
        "historical_reason": row.get("historical_reason"),
        "historical_warning": row.get("historical_warning"),
        "operational_status": row.get("operational_status"),
        "operational_ready": row.get("operational_ready"),
        "operational_score": row.get("operational_score"),
        "operational_blocks": row.get("operational_blocks") or [],
        "operational_warnings": row.get("operational_warnings") or [],
        "operational_summary": row.get("operational_summary"),
        "conviction_score": row.get("conviction_score"),
        "conviction_level": row.get("conviction_level"),
        "conviction_summary": row.get("conviction_summary"),
        "conviction_factors": row.get("conviction_factors") or [],
        "conviction_conflicts": row.get("conviction_conflicts") or [],
        "priority_score": row.get("priority_score"),
        "priority_level": row.get("priority_level"),
        "priority_rank": row.get("priority_rank"),
        "priority_summary": row.get("priority_summary"),
        "priority_factors": row.get("priority_factors") or [],
        "final_decision": row.get("final_decision"),
        "final_decision_score": row.get("final_decision_score"),
        "final_decision_summary": row.get("final_decision_summary"),
        "final_decision_reason": row.get("final_decision_reason"),
        "final_decision_blocks": row.get("final_decision_blocks") or [],
        "final_decision_confidence": row.get("final_decision_confidence"),
    }


def summarize_snapshot_rows(rows: Iterable[Any]) -> dict[str, int]:
    safe_rows = [row for row in rows or [] if isinstance(row, dict)]
    actionable_rows = [row for row in safe_rows if is_actionable_snapshot_row(row)]
    bullish_candidates = [
        row for row in safe_rows if snapshot_row_orientation(row) == "bullish"
    ]
    bearish_candidates = [
        row for row in safe_rows if snapshot_row_orientation(row) == "bearish"
    ]
    actionable_bullish = [
        row for row in actionable_rows if snapshot_row_orientation(row) == "bullish"
    ]
    actionable_bearish = [
        row for row in actionable_rows if snapshot_row_orientation(row) == "bearish"
    ]
    blocked_signals = [row for row in safe_rows if is_blocked_snapshot_row(row)]
    watchlist_candidates = [row for row in safe_rows if is_watchlist_snapshot_row(row)]

    return {
        "total_signals": len(safe_rows),
        "candidates": len(safe_rows),
        "bullish_candidates": len(bullish_candidates),
        "bearish_candidates": len(bearish_candidates),
        "actionable": len(actionable_rows),
        "actionable_bullish": len(actionable_bullish),
        "actionable_bearish": len(actionable_bearish),
        "blocked_signals": len(blocked_signals),
        "watchlist_candidates": len(watchlist_candidates),
        "bullish": len(actionable_bullish),
        "bearish": len(actionable_bearish),
    }


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
