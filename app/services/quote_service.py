from __future__ import annotations

import math
import re
from typing import Any

from app.cache.snapshot_cache import get_last_good_snapshot_ticker, get_snapshot_ticker
from app.market.market_data_loader import get_cached_price_snapshots, get_display_symbol
from app.system.system_metrics import record_cache_access


def _normalize_symbol(symbol: str | None) -> str:
    return str(symbol or "").upper().strip()


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
    candidates = [ticker, display]

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


def classify_quote_payload(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict) or not payload:
        return "empty"

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
    return {
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
        "source": source,
        "quote_status": status,
        "reference_symbol": row.get("reference_symbol"),
        "reference_proxy_for": row.get("reference_proxy_for"),
        "exact_contract": row.get("exact_contract"),
        "stale": status == "stale" or bool(row.get("stale")),
    }


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


def empty_quote_payload(symbol: str) -> dict[str, Any]:
    display_symbol = get_display_symbol(_normalize_symbol(symbol))
    return {
        "symbol": display_symbol,
        "price": None,
        "change": None,
        "change_pct": None,
        "after_hours": None,
        "pre_market": None,
        "volume": None,
        "high": None,
        "low": None,
        "source": "empty",
        "quote_status": "empty",
        "stale": False,
    }
