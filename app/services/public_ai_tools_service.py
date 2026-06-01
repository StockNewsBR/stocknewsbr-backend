from __future__ import annotations

import time
from typing import Any

from app.ai.feature_hub import build_ai_tool_payload
from app.cache.snapshot_cache import get_snapshot
from app.services.quote_service import get_cached_quote_payload
from app.services.ai_alert_history_service import (
    AI_ALERT_MAX_ROWS_PER_TOOL,
    AI_ALERT_RESET_HOUR,
    AI_ALERT_TZ,
    AI_TOOL_KEYS,
    get_ai_alert_history_snapshot,
    get_ai_alert_reset_key,
)
from app.watchlists.watchlist_default import WATCHLIST_B3, WATCHLIST_BDR, WATCHLIST_CRYPTO, WATCHLIST_US_GLOBAL


_DERIVED_CACHE_TTL_SECONDS = 12.0
_derived_cache: dict[str, Any] = {"expires_at": 0.0, "symbols": (), "tools": None}


def _safe_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _empty_tools() -> dict[str, list[dict[str, Any]]]:
    return {key: [] for key in AI_TOOL_KEYS}


def _snapshot_tools(snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    raw_tools = snapshot.get("ai_tools")
    tools = _empty_tools()
    if not isinstance(raw_tools, dict):
        return tools
    for key in AI_TOOL_KEYS:
        tools[key] = _safe_rows(raw_tools.get(key))[:AI_ALERT_MAX_ROWS_PER_TOOL]
    return tools


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 0:
        return number
    return None


def _is_operational_row(row: dict[str, Any]) -> bool:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    quality = str(
        row.get("data_quality")
        or row.get("dataQuality")
        or metrics.get("data_quality")
        or metrics.get("dataQuality")
        or ""
    ).lower()
    if "score_only" in quality or "missing" in quality or "empty" in quality:
        return False
    return _positive_number(row.get("price") or metrics.get("price")) is not None and _positive_number(row.get("volume") or metrics.get("volume")) is not None


def _has_operational_tools(tools: dict[str, list[dict[str, Any]]]) -> bool:
    return any(_is_operational_row(row) for rows in tools.values() for row in rows)


def _normalize_symbol(symbol: Any) -> str:
    return str(symbol or "").upper().strip()


def _dedupe_symbols(symbols: list[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for symbol in symbols:
        normalized = _normalize_symbol(symbol)
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return output


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number and number not in (float("inf"), float("-inf")) else default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _quote_feature_row(symbol: str, quote: dict[str, Any]) -> dict[str, Any] | None:
    price = _positive_number(quote.get("price"))
    volume = _positive_number(quote.get("volume"))
    if price is None or volume is None:
        return None

    change_pct = _to_float(quote.get("change_pct"), 0.0)
    change = _to_float(quote.get("change"), price * change_pct / 100.0 if price else 0.0)
    previous_close = price - change if change else price
    high = _positive_number(quote.get("high")) or max(price, previous_close) * (1.0 + max(abs(change_pct), 0.2) / 300.0)
    low = _positive_number(quote.get("low")) or min(price, previous_close) * (1.0 - max(abs(change_pct), 0.2) / 300.0)
    average_volume = _positive_number(quote.get("average_volume") or quote.get("avg_volume"))
    rel_volume = _positive_number(quote.get("rel_volume") or quote.get("rvol"))
    if rel_volume is None and average_volume:
        rel_volume = volume / average_volume
    rel_volume = rel_volume or 1.0
    score = _clamp(50.0 + change_pct * 8.0 + (rel_volume - 1.0) * 8.0, 5.0, 95.0)
    rsi = _clamp(50.0 + change_pct * 4.0, 20.0, 80.0)

    return {
        "ticker": symbol,
        "symbol": symbol,
        "name": symbol,
        "price": price,
        "close": price,
        "last_price": price,
        "prev_close": previous_close if previous_close > 0 else price,
        "high": high,
        "low": low,
        "volume": int(volume),
        "avg_volume": int(average_volume or max(volume / max(rel_volume, 0.01), 1)),
        "average_volume": int(average_volume or max(volume / max(rel_volume, 0.01), 1)),
        "rel_volume": rel_volume,
        "rvol": rel_volume,
        "change": change,
        "change_pct": change_pct,
        "vwap": price,
        "rsi": rsi,
        "score": score,
        "source_score": score,
        "data_quality": "priced",
        "quote_status": quote.get("quote_status") or "valid",
        "market_data_updated_at": quote.get("market_data_updated_at") or quote.get("quote_time") or quote.get("provider_timestamp"),
        "quote_time": quote.get("quote_time") or quote.get("market_data_updated_at") or quote.get("provider_timestamp"),
        "provider_timestamp": quote.get("provider_timestamp") or quote.get("market_data_updated_at") or quote.get("quote_time"),
    }


def _derive_tools_from_cached_quotes(extra_symbols: list[Any] | None = None) -> dict[str, list[dict[str, Any]]]:
    symbols = _dedupe_symbols([
        *(extra_symbols or []),
        *WATCHLIST_B3,
        *WATCHLIST_BDR,
        *WATCHLIST_US_GLOBAL,
        *WATCHLIST_CRYPTO,
    ])
    now = time.monotonic()
    cache_symbols = tuple(symbols)
    if _derived_cache.get("tools") is not None and _derived_cache.get("symbols") == cache_symbols and float(_derived_cache.get("expires_at") or 0.0) > now:
        return _derived_cache["tools"]

    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        quote = get_cached_quote_payload(symbol)
        if not isinstance(quote, dict):
            continue
        row = _quote_feature_row(symbol, quote)
        if row:
            rows.append(row)

    tools = build_ai_tool_payload(rows, rows, limit=AI_ALERT_MAX_ROWS_PER_TOOL) if rows else _empty_tools()
    for tool, tool_rows in tools.items():
        for row in tool_rows:
            row.setdefault("data_quality", "priced")
            feature = next((item for item in rows if item.get("ticker") == row.get("ticker") or item.get("symbol") == row.get("ticker")), None)
            if feature:
                row.setdefault("market_data_updated_at", feature.get("market_data_updated_at"))
                row.setdefault("quote_time", feature.get("quote_time"))
                row.setdefault("provider_timestamp", feature.get("provider_timestamp"))
            metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
            metrics.setdefault("data_quality", "priced")
            row["metrics"] = metrics

    _derived_cache.update({"expires_at": now + _DERIVED_CACHE_TTL_SECONDS, "symbols": cache_symbols, "tools": tools})
    return tools


def build_public_ai_tools_payload(extra_symbols: list[Any] | None = None) -> dict[str, Any]:
    snapshot = get_snapshot()
    tools = _snapshot_tools(snapshot if isinstance(snapshot, dict) else {})
    if _has_operational_tools(tools):
        return {
            "reset_key": get_ai_alert_reset_key(),
            "updated_at": snapshot.get("updated_at") or snapshot.get("generated_at"),
            "max_rows_per_tool": AI_ALERT_MAX_ROWS_PER_TOOL,
            "reset_hour": AI_ALERT_RESET_HOUR,
            "timezone": str(AI_ALERT_TZ),
            "source": "snapshot",
            "tools": tools,
        }

    payload = dict(get_ai_alert_history_snapshot())
    history_tools = payload.setdefault("tools", _empty_tools())
    if _has_operational_tools(history_tools):
        payload.setdefault("source", "history")
        return payload

    derived_tools = _derive_tools_from_cached_quotes(extra_symbols)
    if _has_operational_tools(derived_tools):
        return {
            "reset_key": get_ai_alert_reset_key(),
            "updated_at": snapshot.get("updated_at") or snapshot.get("generated_at"),
            "max_rows_per_tool": AI_ALERT_MAX_ROWS_PER_TOOL,
            "reset_hour": AI_ALERT_RESET_HOUR,
            "timezone": str(AI_ALERT_TZ),
            "source": "quote_cache_derived",
            "tools": derived_tools,
        }

    payload.setdefault("source", "history")
    return payload
