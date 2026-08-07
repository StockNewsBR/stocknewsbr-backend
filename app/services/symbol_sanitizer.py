from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from threading import RLock
from typing import Any

from app.services.symbol_registry import CRYPTO_BASES
from app.services.symbol_registry import US_EXCHANGE_BY_SYMBOL
from app.services.symbol_registry import canonical_symbol_or_none
from app.services.symbol_registry import has_us_market_qualifier
from app.services.symbol_registry import is_ambiguous_crypto_symbol
from app.services.symbol_registry import is_known_bdr_symbol


DEFAULT_SYMBOL_COOLDOWN_SECONDS = 300

_QUERY_TOKENS = ("interval=", "limit=", "period=", "range=", "symbol=", "ticker=")
_QUERY_NAMES = {"INTERVAL", "LIMIT", "PERIOD", "RANGE", "SYMBOL", "TICKER"}
_BLOCKED_CHARS = ("&", "?", "/", "\\")
_B3_RE = re.compile(r"^[A-Z][A-Z0-9]{3,4}(3|4|5|6|7|11|34)$")
_B3_FUTURE_RE = re.compile(r"^(WIN|WDO)[FGHJKMNQUVXZ]\d{2}$")
_CRYPTO_RE = re.compile(r"^[A-Z]{2,8}(USD|USDT)$")
_CRYPTO_PROVIDER_RE = re.compile(r"^[A-Z0-9]{2,8}-USD$")
_US_RE = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")
_CME_PROVIDER_RE = re.compile(r"^[A-Z]{1,4}=F$")

# Index/FX provider symbols served on the top strip. Anything not listed here is
# rejected before reaching the provider, which is why the US indices came back
# empty while ^BVSP worked.
_PROVIDER_SYMBOLS = {"^BVSP", "BRL=X", "^GSPC", "^IXIC", "^DJI", "^RUT"}
_PERMANENT_BLOCKLIST = {
    "GOLL4",
    "GOLL4.SA",
}

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_COOLDOWN_FILE = Path(os.getenv("SYMBOL_COOLDOWN_FILE") or _PROJECT_ROOT / "runtime" / "cache" / "symbol_cooldowns.json")

_cooldowns: dict[str, dict[str, Any]] = {}
_lock = RLock()
_shared_file_sig: tuple[int, int] | None = None
_last_shared_sync: float = 0.0


def _raw(value: Any) -> str:
    return str(value or "").strip().upper()


def _cooldown_key(value: Any) -> str:
    return _raw(value)[:80]


def _sync_shared_cooldowns(now: float) -> None:
    global _shared_file_sig, _last_shared_sync
    if now - _last_shared_sync < 0.2 and _cooldowns:
        return
    _last_shared_sync = now
    try:
        if not _COOLDOWN_FILE.exists():
            return
        stat = _COOLDOWN_FILE.stat()
        sig = (stat.st_mtime_ns, stat.st_size)
        if _shared_file_sig == sig:
            return
        raw_text = _COOLDOWN_FILE.read_text(encoding="utf-8")
        loaded = json.loads(raw_text)
        if isinstance(loaded, dict):
            for k, v in loaded.items():
                if isinstance(v, dict) and float(v.get("until") or 0.0) > now:
                    if k not in _cooldowns and len(_cooldowns) >= 4096:
                        _cooldowns.pop(next(iter(_cooldowns)))
                    _cooldowns[k] = v
        _shared_file_sig = sig
    except Exception:
        pass


def _persist_shared_cooldowns() -> None:
    global _shared_file_sig
    now = time.time()
    active = {
        k: v for k, v in _cooldowns.items()
        if isinstance(v, dict) and float(v.get("until") or 0.0) > now
    }
    try:
        _COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = _COOLDOWN_FILE.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(active, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_file, _COOLDOWN_FILE)
        stat = _COOLDOWN_FILE.stat()
        _shared_file_sig = (stat.st_mtime_ns, stat.st_size)
    except Exception:
        pass


def mark_symbol_cooldown(value: Any, reason: str = "provider_failure", seconds: int = DEFAULT_SYMBOL_COOLDOWN_SECONDS) -> None:
    key = _cooldown_key(value)
    if not key:
        return
    with _lock:
        if key not in _cooldowns and len(_cooldowns) >= 4096:
            # Prevent cardinality explosion by evicting oldest
            _cooldowns.pop(next(iter(_cooldowns)))
        _cooldowns[key] = {
            "until": time.time() + max(60, int(seconds or DEFAULT_SYMBOL_COOLDOWN_SECONDS)),
            "reason": str(reason or "provider_failure")[:120],
        }
        _persist_shared_cooldowns()


def clear_symbol_cooldown(value: Any) -> None:
    key = _cooldown_key(value)
    if not key:
        return
    with _lock:
        _cooldowns.pop(key, None)
        _persist_shared_cooldowns()


def is_symbol_on_cooldown(value: Any, *, now: float | None = None) -> bool:
    key = _cooldown_key(value)
    if not key:
        return False
    current_time = time.time() if now is None else float(now)
    with _lock:
        item = _cooldowns.get(key)
        if isinstance(item, dict) and float(item.get("until") or 0.0) > current_time:
            return True
        _sync_shared_cooldowns(current_time)
        item = _cooldowns.get(key)
        if isinstance(item, dict) and float(item.get("until") or 0.0) > current_time:
            return True
        return False


def symbol_cooldown_snapshot() -> dict[str, dict[str, Any]]:
    now = time.time()
    with _lock:
        _sync_shared_cooldowns(now)
        return {
            key: dict(value)
            for key, value in _cooldowns.items()
            if isinstance(value, dict) and float(value.get("until") or 0.0) > now
        }


def is_permanently_blocked_symbol(value: Any) -> bool:
    raw = _raw(value)
    compact = raw[:-3] if raw.endswith(".SA") else raw
    return raw in _PERMANENT_BLOCKLIST or compact in _PERMANENT_BLOCKLIST


def _crypto_base(value: Any) -> str | None:
    raw = _raw(value)
    if _CRYPTO_PROVIDER_RE.match(raw):
        return raw[:-4]
    compact = raw.replace("-USD", "USD")
    if compact.endswith("USDT"):
        return compact[:-4]
    if compact.endswith("USD"):
        return compact[:-3]
    return None


def crypto_provider_symbol(value: Any) -> str | None:
    sanitized = sanitize_market_symbol(value, allow_provider_symbols=True)
    if not sanitized:
        return None
    base = _crypto_base(sanitized)
    if not base or not re.fullmatch(r"[A-Z0-9]{2,8}", base):
        return None
    return f"{base}-USD"


def crypto_display_symbol(value: Any) -> str | None:
    sanitized = sanitize_market_symbol(value, allow_provider_symbols=True)
    if not sanitized:
        return None
    base = _crypto_base(sanitized)
    if not base or not re.fullmatch(r"[A-Z0-9]{2,8}", base):
        return None
    return f"{base}USD"


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
    if is_ambiguous_crypto_symbol(raw):
        return None

    if allow_provider_symbols:
        if raw in _PROVIDER_SYMBOLS or _CME_PROVIDER_RE.match(raw):
            return raw
        if raw.endswith(".SA") and sanitize_market_symbol(raw[:-3]):
            return raw
        if "=" in raw:
            return None

    canonical = canonical_symbol_or_none(raw)
    if canonical:
        return canonical

    if has_us_market_qualifier(raw):
        qualified_symbol = raw[:-3] if raw.endswith(".US") else raw
        if ":" in qualified_symbol:
            qualified_symbol = qualified_symbol.rsplit(":", 1)[-1].strip()
        if qualified_symbol in CRYPTO_BASES and qualified_symbol not in US_EXCHANGE_BY_SYMBOL:
            return None
        if _crypto_base(qualified_symbol) in CRYPTO_BASES:
            return None
        if qualified_symbol.endswith("34"):
            return None
        if (
            (_B3_RE.match(qualified_symbol) or _B3_FUTURE_RE.match(qualified_symbol))
            and qualified_symbol not in US_EXCHANGE_BY_SYMBOL
        ):
            return None
        raw = qualified_symbol

    if _looks_like_query(raw):
        return None
    if is_permanently_blocked_symbol(raw):
        return None

    compact = raw[:-3] if raw.endswith(".SA") else raw
    compact = compact.replace("-USD", "USD")
    if compact.endswith("USDT"):
        compact = f"{compact[:-4]}USD"
    if compact in CRYPTO_BASES:
        return None
    if compact.endswith("34") and not is_known_bdr_symbol(compact):
        return None

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
