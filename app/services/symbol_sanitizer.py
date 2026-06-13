from __future__ import annotations

import re
import time
from threading import RLock
from typing import Any


DEFAULT_SYMBOL_COOLDOWN_SECONDS = 300

_QUERY_TOKENS = ("interval=", "limit=", "period=", "range=", "symbol=", "ticker=")
_QUERY_NAMES = {"INTERVAL", "LIMIT", "PERIOD", "RANGE", "SYMBOL", "TICKER"}
_BLOCKED_CHARS = ("&", "?", "/", "\\")
_B3_RE = re.compile(r"^[A-Z]{4,5}(3|4|5|6|11|34)$")
_B3_FUTURE_RE = re.compile(r"^(WIN|WDO)[FGHJKMNQUVXZ]\d{2}$")
_CRYPTO_RE = re.compile(r"^[A-Z]{2,8}(USD|USDT)$")
_US_RE = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")
_CME_PROVIDER_RE = re.compile(r"^[A-Z]{1,4}=F$")

_PROVIDER_SYMBOLS = {"^BVSP", "BRL=X"}
_PERMANENT_BLOCKLIST = {
    "AXIA6",
    "AXIA6.SA",
    "AZUL4",
    "AZUL4.SA",
    "GOLL4",
    "GOLL4.SA",
}

_cooldowns: dict[str, dict[str, Any]] = {}
_lock = RLock()


def _raw(value: Any) -> str:
    return str(value or "").strip().upper()


def _cooldown_key(value: Any) -> str:
    return _raw(value)[:80]


def mark_symbol_cooldown(value: Any, reason: str = "provider_failure", seconds: int = DEFAULT_SYMBOL_COOLDOWN_SECONDS) -> None:
    key = _cooldown_key(value)
    if not key:
        return
    with _lock:
        _cooldowns[key] = {
            "until": time.time() + max(60, int(seconds or DEFAULT_SYMBOL_COOLDOWN_SECONDS)),
            "reason": str(reason or "provider_failure")[:120],
        }


def clear_symbol_cooldown(value: Any) -> None:
    key = _cooldown_key(value)
    if not key:
        return
    with _lock:
        _cooldowns.pop(key, None)


def is_symbol_on_cooldown(value: Any, *, now: float | None = None) -> bool:
    key = _cooldown_key(value)
    if not key:
        return False
    current_time = time.time() if now is None else float(now)
    with _lock:
        item = _cooldowns.get(key)
        if not isinstance(item, dict):
            return False
        return float(item.get("until") or 0.0) > current_time


def symbol_cooldown_snapshot() -> dict[str, dict[str, Any]]:
    now = time.time()
    with _lock:
        return {
            key: dict(value)
            for key, value in _cooldowns.items()
            if isinstance(value, dict) and float(value.get("until") or 0.0) > now
        }


def is_permanently_blocked_symbol(value: Any) -> bool:
    raw = _raw(value)
    compact = raw[:-3] if raw.endswith(".SA") else raw
    return raw in _PERMANENT_BLOCKLIST or compact in _PERMANENT_BLOCKLIST


def _looks_like_query(value: str) -> bool:
    lowered = value.lower()
    return (
        value.startswith("=")
        or value in _QUERY_NAMES
        or any(token in lowered for token in _QUERY_TOKENS)
        or any(char in value for char in _BLOCKED_CHARS)
        or bool(re.search(r"\s", value))
    )


def sanitize_market_symbol(value: Any, *, allow_provider_symbols: bool = False) -> str | None:
    raw = _raw(value)
    if not raw:
        return None
    if _looks_like_query(raw):
        return None
    if is_permanently_blocked_symbol(raw):
        return None

    if allow_provider_symbols:
        if raw in _PROVIDER_SYMBOLS or _CME_PROVIDER_RE.match(raw):
            return raw
        if raw.endswith(".SA") and sanitize_market_symbol(raw[:-3]):
            return raw
        if "=" in raw:
            return None

    compact = raw[:-3] if raw.endswith(".SA") else raw
    compact = compact.replace("-USD", "USD")
    if compact.endswith("USDT"):
        compact = f"{compact[:-4]}USD"

    if compact.startswith("=") or not compact:
        return None
    if compact[0].isdigit():
        return None
    if _B3_RE.match(compact) or _B3_FUTURE_RE.match(compact) or _CRYPTO_RE.match(compact) or _US_RE.match(compact):
        return compact
    return None


def sanitize_market_symbols(values: Any, *, allow_provider_symbols: bool = False) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        items = [values]
    else:
        try:
            items = list(values or [])
        except TypeError:
            items = [values]
    seen: set[str] = set()
    result: list[str] = []
    for value in items:
        sanitized = sanitize_market_symbol(value, allow_provider_symbols=allow_provider_symbols)
        if sanitized and sanitized in seen:
            continue
        if sanitized and is_symbol_on_cooldown(sanitized):
            mark_symbol_cooldown(sanitized, "cooldown")
            continue
        if sanitized:
            seen.add(sanitized)
            result.append(sanitized)
        elif value:
            mark_symbol_cooldown(value, "invalid_symbol")
    return result
