from __future__ import annotations

import math
import re
from typing import Any

from app.cache.snapshot_cache import get_last_good_snapshot_ticker, get_snapshot_ticker
from app.market.market_data_loader import get_cached_price_snapshots, get_display_symbol, get_price_snapshot
from app.services.symbol_registry import canonical_symbol, canonical_symbol_aliases, is_ambiguous_crypto_symbol
from app.services.symbol_sanitizer import mark_symbol_cooldown, sanitize_market_symbol
from app.system.system_metrics import record_cache_access


def _normalize_symbol(symbol: str | None) -> str:
    if is_ambiguous_crypto_symbol(symbol):
        mark_symbol_cooldown(symbol, "ambiguous_symbol")
        return ""
    sanitized = canonical_symbol(symbol) or sanitize_market_symbol(symbol, allow_provider_symbols=True)
    if not sanitized and symbol:
        mark_symbol_cooldown(symbol, "invalid_symbol")
    return sanitized or ""


def _safe_display_symbol(symbol: str | None) -> str:
    normalized = _normalize_symbol(symbol)
    if normalized:
        display = get_display_symbol(normalized)
        if display:
            return display
    raw = str(symbol or "").upper().strip()
    if not raw:
        return "INVALID_SYMBOL"
    safe = re.sub(r"[^A-Z0-9._=-]", "", raw)[:32]
    return safe or "INVALID_SYMBOL"


_CME_FUTURES_PROVIDER_SYMBOLS = {
    "NQ": "NQ=F",
    "MNQ": "MNQ=F",
    "MNO": "MNQ=F",
    "ES": "ES=F",
    "MES": "MES=F",
    "YM": "YM=F",
    "MYM": "MYM=F",
}

_B3_MINI_FUTURE_RE = re.compile(r"^(WIN|WDO)[FGHJKMNQUVXZ]\d{2}$")


def _quote_candidates(symbol: str) -> list[str]:
    ticker = _normalize_symbol(symbol)
    display = get_display_symbol(ticker)
    candidates = [*canonical_symbol_aliases(ticker), ticker, display]

    provider_symbol = _CME_FUTURES_PROVIDER_SYMBOLS.get(ticker)
    if provider_symbol:
        candidates.append(provider_symbol)

    if _B3_MINI_FUTURE_RE.match(ticker):
        candidates.append(f"{ticker}.SA")

    if ticker.endswith(".SA"):
        candidates.append(ticker[:-3])
    elif ticker and "." not in ticker and "-" not in ticker and ticker[-1:].isdigit():
        candidates.append(f"{ticker}.SA")

    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _safe_price(payload: dict[str, Any] | None) -> float | None:
    if not isinstance(payload, dict):
        return None
    try:
        price = float(payload.get("price"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(price) or price <= 0:
        return None
    return price


def _safe_positive_number(payload: dict[str, Any] | None, field: str) -> float | None:
    if not isinstance(payload, dict):
        return None
    try:
        value = float(payload.get(field))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def _safe_finite_number(payload: dict[str, Any] | None, field: str) -> float | None:
    if not isinstance(payload, dict):
        return None
    try:
        value = float(payload.get(field))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def quote_field_diagnostics(payload: dict[str, Any] | None) -> dict[str, Any]:
    field_status = {
        "price": _safe_price(payload) is not None,
        "volume": _safe_positive_number(payload, "volume") is not None,
        "score": _safe_finite_number(payload, "score") is not None
        or _safe_finite_number(payload, "master_score") is not None,
        "rsi": _safe_finite_number(payload, "rsi") is not None,
        "bias": bool(str((payload or {}).get("bias") or (payload or {}).get("trend_bias") or "").strip()),
        "snapshot": isinstance(payload, dict)
        and str(payload.get("source") or "").lower()
        in {"snapshot", "last_good_snapshot", "stale_last_good_snapshot", "market_cache", "market_cache_stale"},
        "quote": is_usable_quote_payload(payload, allow_stale=True),
    }
    missing_fields = [field for field in ("price", "volume", "score", "rsi", "bias") if not field_status[field]]
    quote_missing_fields = [field for field in ("price", "volume") if not field_status[field]]
    return {
        "field_status": field_status,
        "missing_fields": missing_fields,
        "quote_missing_fields": quote_missing_fields,
        "core_data": not quote_missing_fields,
        "strategic_core_data": not missing_fields,
        "snapshot_exists": field_status["snapshot"],
        "quote_exists": field_status["quote"],
    }


def with_quote_diagnostics(payload: dict[str, Any] | None, symbol: str | None = None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    normalized_payload = dict(payload)
    if symbol:
        normalized_payload["symbol"] = _safe_display_symbol(symbol)
    diagnostics = quote_field_diagnostics(normalized_payload)
    normalized_payload.update(diagnostics)
    return normalized_payload


QUOTE_STATUS_ALLOWLIST = {
    "empty",
    "ambiguous_symbol",
    "blocked_symbol",
    "invalid_symbol",
    "no_data",
    "provider_error",
    "unknown_symbol",
    "unsupported",
}


def _normalize_quote_status(status: str | None, default: str = "empty") -> str:
    normalized = str(status or default).strip().lower()
    return normalized if normalized in QUOTE_STATUS_ALLOWLIST else default


def classify_quote_payload(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict) or not payload:
        return "empty"

    explicit_status = _normalize_quote_status(payload.get("quote_status"), default="")
    if explicit_status and explicit_status != "empty":
        return explicit_status

    has_price = _safe_price(payload) is not None
    if has_price:
        if str(payload.get("quote_status") or "").lower() == "reference" or str(payload.get("source") or "").lower() == "reference_proxy":
            return "reference"
        source = str(payload.get("source") or "").lower()
        if payload.get("stale") is True or source.startswith("stale"):
            return "stale"
        return "valid"

    partial_fields = ("change", "change_pct", "volume", "high", "low", "after_hours", "pre_market")
    if any(payload.get(field) is not None for field in partial_fields):
        return "partial"
    return "empty"


def is_usable_quote_payload(payload: dict[str, Any] | None, *, allow_stale: bool = True) -> bool:
    status = classify_quote_payload(payload)
    return status in {"valid", "reference"} or (allow_stale and status == "stale")


def _payload_from_row(display_symbol: str, row: dict[str, Any], source: str) -> dict[str, Any] | None:
    if not is_usable_quote_payload(row):
        return None

    status = classify_quote_payload(row)
    timestamp = (
        # The producer's own quote timestamp outranks cache bookkeeping: it is what
        # renders "As of 3:13:47 PM GMT-3".
        row.get("quote_time")
        or row.get("market_data_updated_at")
        or row.get("provider_timestamp")
        or row.get("timestamp")
        or row.get("updated_at")
        or row.get("last_seen_at")
        or row.get("created_at")
    )
    payload = {
        "symbol": display_symbol,
        "price": row.get("price"),
        "change": row.get("change"),
        "change_pct": row.get("change_pct"),
        "after_hours": row.get("after_hours"),
        "pre_market": row.get("pre_market"),
        "volume": row.get("volume"),
        "average_volume": row.get("average_volume") or row.get("avg_volume"),
        "avg_volume": row.get("average_volume") or row.get("avg_volume"),
        "rel_volume": row.get("rel_volume") or row.get("rvol"),
        "high": row.get("high"),
        "low": row.get("low"),
        # Baseline + market state; null when the producer had no provider field
        # for it (never inferred).
        "previous_close": row.get("previous_close"),
        "market_state": row.get("market_state"),
        "source": source,
        "quote_status": status,
        "reference_symbol": row.get("reference_symbol"),
        "reference_proxy_for": row.get("reference_proxy_for"),
        "exact_contract": row.get("exact_contract"),
        "stale": status == "stale" or bool(row.get("stale")),
        "market_data_updated_at": timestamp,
        "quote_time": timestamp,
        "provider_timestamp": timestamp,
    }
    for field in (
        "requested_symbol",
        "canonical_symbol",
        "display_symbol",
        "provider_symbol",
        "asset_type",
        "market",
        "currency",
        "timezone",
        "identity_preserved",
        "price_semantics",
        "freshness_semantics",
        "fallback",
        "fallback_type",
    ):
        if row.get(field) is not None:
            payload[field] = row.get(field)
    payload.setdefault("display_symbol", display_symbol)
    return with_quote_diagnostics(payload)


def get_cached_quote_payload(symbol: str) -> dict[str, Any] | None:
    ticker = _normalize_symbol(symbol)
    if not ticker:
        return None

    display_symbol = get_display_symbol(ticker)
    candidates = _quote_candidates(ticker)
    snapshot_row = get_snapshot_ticker(candidates)
    if snapshot_row:
        payload = _payload_from_row(display_symbol, snapshot_row, "snapshot")
        if payload:
            record_cache_access("quote", True, "snapshot")
            return payload

    last_good_row = get_last_good_snapshot_ticker(candidates)
    if last_good_row:
        payload = _payload_from_row(display_symbol, last_good_row, "last_good_snapshot")
        if payload:
            payload["source"] = "stale_last_good_snapshot"
            payload["quote_status"] = "stale"
            payload["stale"] = True
            record_cache_access("quote", True, "last_good_snapshot")
            return payload

    cached_quotes = get_cached_price_snapshots(candidates)
    for candidate in candidates:
        key = get_display_symbol(candidate)
        row = cached_quotes.get(candidate) or cached_quotes.get(key)
        if isinstance(row, dict):
            payload = _payload_from_row(display_symbol, row, row.get("source") or "market_cache")
            if payload:
                record_cache_access("quote", True, payload.get("source") or "market_cache")
                return payload

    record_cache_access("quote", False, "empty")
    return None


def get_quote_payload(symbol: str, *, allow_fetch: bool = False) -> dict[str, Any] | None:
    cached = get_cached_quote_payload(symbol)
    if cached or not allow_fetch:
        return cached

    ticker = _normalize_symbol(symbol)
    if not ticker:
        return None

    for candidate in _quote_candidates(ticker):
        fresh = get_price_snapshot(candidate)
        if not fresh:
            continue
        payload = _payload_from_row(get_display_symbol(ticker), fresh, fresh.get("source") or "on_demand_snapshot")
        if payload:
            payload["source"] = payload.get("source") or "on_demand_snapshot"
            payload["snapshot_status"] = "generated_on_demand"
            return payload

    return get_cached_quote_payload(symbol)


def empty_quote_payload(symbol: str, *, quote_status: str = "empty", reason: str | None = None) -> dict[str, Any]:
    status = _normalize_quote_status(quote_status)
    display_symbol = _safe_display_symbol(symbol)
    source = status if status != "empty" else "empty"
    return with_quote_diagnostics({
        "symbol": display_symbol,
        "price": None,
        "change": None,
        "change_pct": None,
        "after_hours": None,
        "pre_market": None,
        "volume": None,
        "high": None,
        "low": None,
        "previous_close": None,
        "quote_time": None,
        "market_state": None,
        "source": source,
        "quote_status": status,
        "provider_status": reason or status,
        "error_reason": reason or status,
        "stale": False,
    }) or {
        "symbol": display_symbol,
        "price": None,
        "change": None,
        "change_pct": None,
        "source": source,
        "quote_status": status,
        "provider_status": reason or status,
        "error_reason": reason or status,
        "stale": False,
        "core_data": False,
        "strategic_core_data": False,
        "missing_fields": ["price", "volume", "score", "rsi", "bias"],
        "quote_missing_fields": ["price", "volume"],
    }
