from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from app.services.score_display import attach_master_score_display_contract
from app.services.symbol_registry import canonical_symbol, canonicalize_symbol_row


ACTIONABLE_SIGNALS = {"BUY", "SELL", "SHORT", "COVER"}
BULLISH_ACTIONS = {"BUY", "COVER"}
BEARISH_ACTIONS = {"SELL", "SHORT"}
BULLISH_WATCH_SIGNALS = {"WATCH_BUY", "WATCH_LONG", "LONG_WATCH"}
BEARISH_WATCH_SIGNALS = {"WATCH_SHORT", "WATCH_SELL", "SHORT_WATCH"}
WATCH_SIGNALS = {"WATCH", "WAIT", "HOLD"} | BULLISH_WATCH_SIGNALS | BEARISH_WATCH_SIGNALS
NO_TRADE_SIGNALS = {"NO_TRADE", "DO_NOT_TRADE"}
DECISION_READY = "READY"
DECISION_BLOCKED = "BLOCKED"
DECISION_NO_TRADE = "NO_TRADE"
DECISION_STALE_DATA = "STALE_DATA"
DECISION_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
DECISION_CONFLICT = "CONFLICT"
DECISION_ERROR = "ERROR"
CANONICAL_DECISION_STATUSES = {
    DECISION_READY,
    DECISION_BLOCKED,
    DECISION_NO_TRADE,
    DECISION_STALE_DATA,
    DECISION_INSUFFICIENT_DATA,
    DECISION_CONFLICT,
    DECISION_ERROR,
}
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
NON_BLOCKING_DISPLAY_WARNINGS = {
    "master_score_normalized_from_raw_100",
}
BLOCKING_DISPLAY_WARNINGS = {
    "master_score_display_invalid",
    "master_score_display_clamped_below_0",
    "master_score_display_clamped_above_10",
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


def _listify(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item or "").strip()]
    return [str(value).strip()]


def _dedupe(values: Iterable[Any], limit: int | None = None) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        output.append(text)
        if limit is not None and len(output) >= limit:
            break
    return output


def _truthy(value: Any) -> bool:
    if value is True:
        return True
    if value in (False, None, "", 0):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "blocked", "invalid"}


def _plain(value: Any) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _contains_no_trade(value: Any) -> bool:
    text = _plain(value)
    for source, target in (("Ã", "A"), ("Á", "A"), ("À", "A"), ("Â", "A"), ("É", "E"), ("Ê", "E"), ("Í", "I"), ("Ó", "O"), ("Ô", "O"), ("Õ", "O"), ("Ú", "U"), ("Ç", "C")):
        text = text.replace(source, target)
    return "NAO OPERAR AGORA" in text or text in {"NO_TRADE", "DO_NOT_TRADE"}


def _has_explicit_risk_score(row: dict[str, Any]) -> bool:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    return any(value not in (None, "") for value in (row.get("risk_score"), metrics.get("risk_score")))


def _has_risk_context(row: dict[str, Any]) -> bool:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    text = " ".join(
        str(value or "").lower()
        for value in (
            row.get("state"),
            row.get("ai_comment"),
            row.get("reason"),
            row.get("risk_level"),
            row.get("risk_summary"),
            metrics.get("risk_state"),
            metrics.get("risk_summary"),
        )
    )
    return any(
        token in text
        for token in (
            "risk",
            "risco",
            "critical",
            "critico",
            "crítico",
            "high",
            "alto",
            "alta",
            "medium",
            "medio",
            "médio",
            "moderado",
            "moderada",
            "low",
            "baixo",
            "baixa",
        )
    )


def normalize_ai_tools_for_decision_context(ai_tools: Any) -> Any:
    if not isinstance(ai_tools, dict):
        return ai_tools

    output: dict[str, Any] = {}
    for tool, rows in ai_tools.items():
        if tool != "risk" or not isinstance(rows, list):
            output[tool] = rows
            continue

        normalized_rows: list[Any] = []
        for row in rows:
            if not isinstance(row, dict):
                normalized_rows.append(row)
                continue
            item = dict(row)
            if "score" in item and not _has_explicit_risk_score(item) and not _has_risk_context(item):
                metrics = dict(item.get("metrics")) if isinstance(item.get("metrics"), dict) else {}
                metrics.setdefault("generic_score", item.pop("score"))
                item["metrics"] = metrics
            normalized_rows.append(item)
        output[tool] = normalized_rows
    return output


def _row_timestamp(row: dict[str, Any], fallback: Any = None) -> Any:
    for key in (
        "timestamp",
        "market_data_updated_at",
        "last_bar_at",
        "quote_time",
        "provider_timestamp",
        "updated_at",
        "generated_at",
        "detected_at",
    ):
        value = row.get(key)
        if value not in (None, ""):
            return value
    if fallback not in (None, ""):
        return fallback
    return datetime.now(timezone.utc).isoformat()


def _source_snapshot_id(row: dict[str, Any], fallback: Any = None) -> Any:
    for key in ("source_snapshot_id", "snapshot_id", "snapshot_timestamp", "generated_at", "updated_at"):
        value = row.get(key)
        if value not in (None, ""):
            return value
    return fallback


def _status_value(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).upper().strip()
    return ""


def _has_conflict(row: dict[str, Any], action: str) -> bool:
    if row.get("conflict_detected") is True or _truthy(row.get("institutional_conflict")):
        return True
    if not master_confirms_signal(row):
        return True
    conflict_values = (
        _listify(row.get("blocked_reasons"))
        + _listify(row.get("warnings"))
        + _listify(row.get("conviction_conflicts"))
        + _listify(row.get("final_decision_blocks"))
    )
    conflict_text = " ".join(conflict_values).lower()
    if any(token in conflict_text for token in ("conflict", "conflito", "master_score_context_not_confirmed", "score_buy_vs_final_short", "score_short_vs_final_buy")):
        return True
    if action in ACTIONABLE_SIGNALS and master_direction_value(row) == "NEUTRAL":
        return True
    return False


def _market_context(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "regime": row.get("regime") or row.get("market_regime") or row.get("market_regime_state") or row.get("chart_regime_state"),
        "trend": row.get("trend") or row.get("trend_bias") or row.get("master_direction"),
        "liquidity": row.get("liquidity_state") or row.get("liquidity_map_state") or row.get("liquidity_event"),
        "risk_level": row.get("risk_level") or row.get("master_risk") or row.get("operational_risk_level"),
        "price": row.get("price") or row.get("close") or row.get("last_price"),
        "volume": row.get("volume") or row.get("last_volume"),
        "source": row.get("source"),
    }


def _decision_human_message(status: str, symbol: str, blockers: list[str], reasons: list[str]) -> str:
    if status == DECISION_READY:
        return f"{symbol}: decisao operacional pronta e auditavel."
    reason = "; ".join((blockers or reasons or ["contexto institucional insuficiente"])[:5])
    if status == DECISION_STALE_DATA:
        return f"{symbol}: NAO OPERAR AGORA. Snapshot stale: {reason}."
    if status == DECISION_CONFLICT:
        return f"{symbol}: NAO OPERAR AGORA. Conflito institucional: {reason}."
    if status == DECISION_INSUFFICIENT_DATA:
        return f"{symbol}: NAO OPERAR AGORA. Dados insuficientes: {reason}."
    return f"{symbol}: NAO OPERAR AGORA. {reason}."


def build_decision_envelope(
    row: Any,
    *,
    snapshot_stale: bool | None = None,
    source_snapshot_id: Any = None,
    timestamp: Any = None,
) -> dict[str, Any]:
    if not isinstance(row, dict):
        now = datetime.now(timezone.utc).isoformat()
        return {
            "symbol": "UNKNOWN",
            "canonical_symbol": None,
            "action": "NO_DECISION",
            "decision_status": DECISION_ERROR,
            "decision_ready": False,
            "confidence": 0.0,
            "master_score": 0.0,
            "master_score_raw": None,
            "data_quality": QUALITY_INVALID,
            "blockers": ["invalid_payload"],
            "blocking_warnings": [],
            "warnings": [],
            "reasons": ["payload invalido"],
            "invalidation_reason": "payload invalido",
            "market_context": {},
            "timestamp": now,
            "source_snapshot_id": source_snapshot_id,
            "human_message": "UNKNOWN: NAO OPERAR AGORA. Payload invalido.",
            "operational_status": None,
            "auditor_status": None,
            "auditor_blocked": False,
            "risk_level": None,
            "regime": None,
            "price_valid": False,
            "volume_valid": False,
            "stale": False,
            "source": None,
        }

    display_row = attach_master_score_display_contract(row)
    resolved_symbol = canonical_symbol(display_row.get("canonical_symbol") or display_row.get("symbol") or display_row.get("ticker"))
    symbol = resolved_symbol or str(display_row.get("symbol") or display_row.get("ticker") or "UNKNOWN").upper().strip() or "UNKNOWN"
    canonical_symbol_value = resolved_symbol or display_row.get("canonical_symbol") or display_row.get("symbol") or display_row.get("ticker")
    action = snapshot_signal_value(display_row) or "NO_DECISION"
    quality = coerce_data_quality(display_row)
    price_valid = has_positive_value(display_row, "price", "close", "last_price")
    volume_valid = has_positive_value(display_row, "volume", "last_volume")
    stale = bool(
        snapshot_stale is True
        or display_row.get("stale") is True
        or display_row.get("is_stale") is True
        or quality == QUALITY_STALE
    )
    auditor_status = audit_status_value(display_row) or None
    auditor_blocked = is_auditor_blocked(display_row)
    operational_status = _status_value(display_row, "operational_status") or None
    final_decision = display_row.get("final_decision")
    decision_state = snapshot_decision_state(display_row)
    blockers: list[str] = []
    snapshot_warnings = _listify(display_row.get("warnings"))
    blocking_warnings = _dedupe(
        _listify(display_row.get("blocking_warnings"))
        + _blocking_warning_values(snapshot_warnings)
    )
    warnings = snapshot_warnings + _listify(display_row.get("operational_warnings")) + _listify(display_row.get("audit_warnings"))

    if stale:
        blockers.append("snapshot_stale")
    if quality in {QUALITY_SCORE_ONLY, QUALITY_EMPTY, QUALITY_INVALID}:
        blockers.append(f"data_quality_{quality}")
    if display_row.get("provider_failed") is True or display_row.get("provider_error"):
        blockers.append("provider_failed")
    if not price_valid:
        blockers.append("price_invalid")
    if not volume_valid:
        blockers.append("volume_invalid")
    if auditor_blocked:
        blockers.append("auditor_blocked")
    if master_status_value(display_row) == "BLOCKED":
        blockers.append("master_score_blocked")
    if operational_status == "BLOCKED":
        blockers.extend(_listify(display_row.get("operational_blocks")) or ["operational_blocked"])
    if display_row.get("radar_no_trade_now") is True:
        blockers.extend(_listify(display_row.get("radar_blocked_reasons")) or ["radar_blocked"])
    if display_row.get("ranking_eligible") is False:
        blockers.extend(_listify(display_row.get("ranking_excluded_reasons")) or ["ranking_excluded"])
    if _contains_no_trade(final_decision):
        blockers.extend(_listify(display_row.get("final_decision_blocks")) or ["final_decision_no_trade"])
    if _has_conflict(display_row, action):
        blockers.append("decision_conflict")
    blockers.extend(blocking_warnings)
    blockers.extend(_listify(display_row.get("blocked_reasons")))
    blockers = _dedupe(blockers)

    if stale:
        status = DECISION_STALE_DATA
    elif any(reason.startswith("data_quality_") or reason in {"price_invalid", "volume_invalid", "provider_failed"} for reason in blockers):
        status = DECISION_INSUFFICIENT_DATA
    elif any("conflict" in reason.lower() or "conflito" in reason.lower() for reason in blockers):
        status = DECISION_CONFLICT
    elif blockers:
        status = DECISION_BLOCKED
    elif action not in ACTIONABLE_SIGNALS or decision_state in BLOCKED_DECISION_STATES:
        status = DECISION_NO_TRADE
    elif display_row.get("decision_ready") is not True:
        status = DECISION_NO_TRADE
    else:
        status = DECISION_READY

    decision_ready = bool(status == DECISION_READY)
    confidence = safe_float(
        display_row.get("confidence")
        or display_row.get("trade_confidence")
        or display_row.get("final_decision_score")
        or display_row.get("priority_score"),
        0.0,
    )
    reasons = _dedupe(
        _listify(display_row.get("no_trade_reasons"))
        + _listify(display_row.get("final_decision_reason"))
        + _listify(display_row.get("ranking_reason"))
        + _listify(display_row.get("radar_reason"))
        + _listify(display_row.get("master_summary"))
        + blockers,
        limit=12,
    )
    invalidation_reason = (
        display_row.get("invalidation_reason")
        or display_row.get("invalidation")
        or display_row.get("invalidacao")
        or "; ".join(_listify(display_row.get("opinion_change_conditions"))[:4])
        or ("; ".join(blockers[:4]) if blockers else "")
    )
    market_context = _market_context(display_row)

    return {
        "symbol": symbol,
        "canonical_symbol": canonical_symbol_value,
        "action": action,
        "decision_status": status,
        "decision_ready": decision_ready,
        "confidence": round(confidence, 2),
        "master_score": display_row.get("master_score"),
        "master_score_raw": display_row.get("master_score_raw"),
        "data_quality": quality,
        "blockers": blockers,
        "blocking_warnings": _dedupe(blocking_warnings),
        "warnings": _dedupe(warnings),
        "reasons": reasons,
        "invalidation_reason": invalidation_reason,
        "market_context": market_context,
        "timestamp": _row_timestamp(display_row, fallback=timestamp),
        "source_snapshot_id": _source_snapshot_id(display_row, fallback=source_snapshot_id),
        "human_message": _decision_human_message(status, symbol, blockers, reasons),
        "operational_status": operational_status,
        "auditor_status": auditor_status,
        "auditor_blocked": auditor_blocked,
        "risk_level": market_context.get("risk_level"),
        "regime": market_context.get("regime"),
        "price_valid": price_valid,
        "volume_valid": volume_valid,
        "stale": stale,
        "source": display_row.get("source"),
    }


def attach_decision_envelope(
    row: dict[str, Any],
    *,
    snapshot_stale: bool | None = None,
    source_snapshot_id: Any = None,
    timestamp: Any = None,
) -> dict[str, Any]:
    item = canonicalize_symbol_row(dict(row))
    envelope = build_decision_envelope(
        item,
        snapshot_stale=snapshot_stale,
        source_snapshot_id=source_snapshot_id,
        timestamp=timestamp,
    )
    item["decision_envelope"] = envelope
    item["decision_status"] = envelope["decision_status"]
    item["decision_ready"] = bool(envelope["decision_ready"])
    item["source_snapshot_id"] = envelope.get("source_snapshot_id")
    item["canonical_symbol"] = envelope.get("canonical_symbol")
    item["ticker"] = envelope.get("canonical_symbol") or item.get("ticker")
    item["symbol"] = envelope.get("canonical_symbol") or item.get("symbol")
    return item


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


def _blocking_warning_values(warnings: Any) -> list[str]:
    return [
        warning
        for warning in _listify(warnings)
        if warning in BLOCKING_DISPLAY_WARNINGS
    ]


def has_blocking_reasons(row: dict[str, Any]) -> bool:
    envelope = row.get("decision_envelope") if isinstance(row.get("decision_envelope"), dict) else {}
    display_warnings = _listify(row.get("warnings"))
    display_blocking_warnings: list[str] = []
    if any(key in row for key in ("master_score_raw", "master_score", "score", "master_score_display")):
        display_row = attach_master_score_display_contract(row)
        display_warnings = _dedupe(display_warnings + _listify(display_row.get("warnings")))
        display_blocking_warnings = _listify(display_row.get("blocking_warnings"))
    blocking_warnings = _dedupe(
        _listify(row.get("blocking_warnings"))
        + display_blocking_warnings
        + _listify(envelope.get("blocking_warnings") if envelope else None)
        + _blocking_warning_values(envelope.get("warnings") if envelope else None)
        + _blocking_warning_values(display_warnings)
    )
    reasons = (
        _listify(row.get("blocked_reasons"))
        + _listify(row.get("blockers"))
        + _listify(envelope.get("blockers") if envelope else None)
        + _listify(blocking_warnings)
    )
    return any(str(item).strip() for item in reasons)


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
    envelope = build_decision_envelope(row)
    if envelope.get("decision_status") != DECISION_READY or envelope.get("decision_ready") is not True:
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

    envelope = build_decision_envelope(row)
    if envelope.get("decision_status") in {
        DECISION_BLOCKED,
        DECISION_STALE_DATA,
        DECISION_INSUFFICIENT_DATA,
        DECISION_CONFLICT,
        DECISION_ERROR,
    }:
        return True

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
    envelope = build_decision_envelope(score_display_contract)
    return {
        "ticker": canonical_symbol(row.get("ticker") or row.get("symbol")) or row.get("ticker") or row.get("symbol"),
        "symbol": canonical_symbol(row.get("symbol") or row.get("ticker")) or row.get("symbol") or row.get("ticker"),
        "canonical_symbol": canonical_symbol(row.get("canonical_symbol") or row.get("ticker") or row.get("symbol")) or row.get("canonical_symbol"),
        "score": row.get("score"),
        "signal": row.get("signal"),
        "trade_action": row.get("trade_action"),
        "decision_ready": row.get("decision_ready"),
        "decision_status": envelope.get("decision_status"),
        "decision_envelope": envelope,
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
    output = [attach_decision_envelope(dict(row)) for row in rows or [] if is_actionable_snapshot_row(row)]
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
    output = attach_decision_envelope(canonicalize_symbol_row(dict(row)))
    ticker = output.get("canonical_symbol") or output.get("ticker") or output.get("symbol")
    if ticker:
        output["ticker"] = ticker
        output["symbol"] = ticker
    output["events"] = normalize_snapshot_events(output.get("events"))
    return output
