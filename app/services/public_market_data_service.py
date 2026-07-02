from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

from app.market.market_data_loader import (
    get_cached_chart_data,
    get_cached_price_snapshots,
)
from app.services.symbol_registry import (
    canonical_symbol,
    canonical_symbol_aliases,
    is_ambiguous_crypto_symbol,
    is_bdr_proxy_payload,
    is_bdr_symbol,
)
from app.services.symbol_sanitizer import mark_symbol_cooldown, sanitize_market_symbol
from app.system.system_metrics import record_cache_access

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_QUOTE_CACHE_FILE = Path(os.getenv("MARKET_QUOTES_CACHE_FILE") or _PROJECT_ROOT / "runtime" / "cache" / "market_quotes.json")
_CHART_CACHE_FILE = Path(os.getenv("MARKET_CHARTS_CACHE_FILE") or _PROJECT_ROOT / "runtime" / "cache" / "market_charts.json")
_QUOTE_DIRECT_MAX_AGE_SECONDS = 60 * 60 * 24 * 7
_CHART_DIRECT_MAX_AGE_SECONDS = 60 * 60 * 24 * 14


def _read_json_cache(path: Path) -> dict:
    for attempt in range(3):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except PermissionError:
            time.sleep(0.025 * (attempt + 1))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
    return {}


def _finite_positive(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _fresh_enough(entry: dict, allow_stale: bool, max_age_seconds: int) -> bool:
    if allow_stale:
        return True
    timestamp = _finite_positive(entry.get("timestamp"))
    if timestamp is None:
        return False
    return (time.time() - timestamp) <= max_age_seconds


def _symbol_aliases(symbol: str) -> list[str]:
    if is_ambiguous_crypto_symbol(symbol):
        return []
    raw = canonical_symbol(symbol) or sanitize_market_symbol(symbol, allow_provider_symbols=True) or ""
    if not raw:
        if symbol:
            mark_symbol_cooldown(symbol, "invalid_symbol")
        return []
    compact = raw.replace(".SA", "").replace("-", "").replace("/", "")
    aliases = [*canonical_symbol_aliases(raw), raw, compact]
    if compact and compact != raw:
        aliases.append(f"{compact}.SA")
    if compact.endswith("USDT"):
        aliases.extend([compact[:-1], f"{compact[:-1][:3]}-USD"])
    if compact.endswith("USD") and len(compact) > 3:
        base = compact[:-3]
        aliases.extend([f"{base}USDT", f"{base}-USD"])
    if compact and compact[-1:].isdigit() and not compact.endswith(".SA"):
        aliases.append(f"{compact}.SA")
    seen: set[str] = set()
    result: list[str] = []
    for alias in aliases:
        normalized = str(alias or "").upper().strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _payload_matches_symbol(payload: dict, symbol: str) -> bool:
    if is_bdr_symbol(symbol):
        if is_bdr_proxy_payload(payload):
            return False

    allowed: set[str] = set()
    for alias in _symbol_aliases(symbol):
        normalized = str(alias or "").upper().strip()
        if not normalized:
            continue
        allowed.add(normalized)
        allowed.add(normalized.replace(".SA", ""))

    identities: set[str] = set()
    for key in ("requested_symbol", "canonical_symbol", "display_symbol", "symbol", "ticker"):
        value = payload.get(key)
        normalized = str(value or "").upper().strip()
        if not normalized:
            continue
        identities.add(normalized)
        identities.add(normalized.replace(".SA", ""))

    source = str(payload.get("source") or "").lower().strip()
    fallback_type = str(payload.get("fallback_type") or "").lower().strip()
    if source in {"proxy_market", "reference_proxy"} or fallback_type:
        return False

    if identities:
        return bool(allowed.intersection(identities))
    for key in ("provider_symbol", "reference_symbol", "exact_contract"):
        value = payload.get(key)
        normalized = str(value or "").upper().strip()
        if not normalized:
            continue
        identities.add(normalized)
        identities.add(normalized.replace(".SA", ""))
    return bool(identities and allowed.intersection(identities))


def _direct_cached_price_payloads(symbols: list[str], allow_stale: bool) -> dict:
    raw_cache = _read_json_cache(_QUOTE_CACHE_FILE)
    if not isinstance(raw_cache, dict):
        return {}

    resolved: dict = {}
    for symbol in symbols:
        for alias in _symbol_aliases(symbol):
            entry = raw_cache.get(alias)
            if not isinstance(entry, dict):
                entry = raw_cache.get(alias.replace(".SA", ""))
            if not isinstance(entry, dict) or not _fresh_enough(entry, allow_stale, _QUOTE_DIRECT_MAX_AGE_SECONDS):
                continue
            payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else entry
            if not isinstance(payload, dict) or _finite_positive(payload.get("price")) is None:
                continue
            if not _payload_matches_symbol(payload, symbol):
                continue

            enriched = dict(payload)
            timestamp = _finite_positive(entry.get("timestamp"))
            if timestamp is not None:
                enriched["cache_age_seconds"] = round(max(0.0, time.time() - timestamp), 3)
                enriched["stale"] = (time.time() - timestamp) > 300
            for key in [symbol, alias, enriched.get("symbol"), enriched.get("display_symbol"), enriched.get("provider_symbol")]:
                if key:
                    resolved[str(key).upper().strip()] = enriched
                    resolved[str(key).upper().replace(".SA", "").strip()] = enriched
            break
    return resolved


def _payload_matches_cache_key(payload: dict, key: str, valid_symbols: list[str] | None = None) -> bool:
    normalized_key = str(key or "").upper().strip()
    if not normalized_key:
        return False
    candidates = valid_symbols or [normalized_key]
    for symbol in candidates:
        aliases = set()
        for alias in _symbol_aliases(symbol):
            aliases.add(alias)
            aliases.add(alias.replace(".SA", ""))
        if normalized_key not in aliases and normalized_key.replace(".SA", "") not in aliases:
            continue
        if _payload_matches_symbol(payload, symbol):
            return True
    return False


def _validated_cache_symbols(symbols: list[str]) -> list[str]:
    valid: list[str] = []
    seen: set[str] = set()
    for symbol in symbols or []:
        normalized = str(symbol or "").upper().strip()
        if not normalized:
            continue
        if is_ambiguous_crypto_symbol(normalized):
            mark_symbol_cooldown(normalized, "ambiguous_symbol")
            continue
        if not _symbol_aliases(normalized):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        valid.append(normalized)
    return valid


def _direct_cached_chart_data(alias: str, interval: str, allow_stale: bool) -> list[dict]:
    raw_cache = _read_json_cache(_CHART_CACHE_FILE)
    charts = raw_cache.get("charts") if isinstance(raw_cache, dict) else None
    if not isinstance(charts, dict):
        return []

    for candidate in _symbol_aliases(alias):
        entry = charts.get(f"{candidate}:{interval}") or charts.get(f"{candidate.replace('.SA', '')}:{interval}")
        if not isinstance(entry, dict) or not _fresh_enough(entry, allow_stale, _CHART_DIRECT_MAX_AGE_SECONDS):
            continue
        rows = entry.get("rows")
        if isinstance(rows, list) and rows:
            return rows
    return []


def cached_price_payloads(symbols: list[str], allow_stale: bool = False) -> dict:
    valid_symbols = _validated_cache_symbols(symbols)
    if not valid_symbols:
        return {}
    direct = {
        key: payload
        for key, payload in _direct_cached_price_payloads(valid_symbols, allow_stale=allow_stale).items()
        if isinstance(payload, dict) and _payload_matches_cache_key(payload, key, valid_symbols)
    }
    try:
        cached = {
            key: payload
            for key, payload in get_cached_price_snapshots(valid_symbols, allow_stale=allow_stale).items()
            if isinstance(payload, dict) and _payload_matches_cache_key(payload, key, valid_symbols)
        }
        if cached:
            merged = dict(cached)
            for key, payload in direct.items():
                current = merged.get(key)
                if not isinstance(current, dict) or _finite_positive(current.get("price")) is None:
                    merged[key] = payload
            for symbol in valid_symbols:
                if any(
                    isinstance(merged.get(alias), dict) and _finite_positive(merged[alias].get("price")) is not None
                    for alias in _symbol_aliases(symbol)
                ):
                    continue
                for alias in _symbol_aliases(symbol):
                    fallback = direct.get(alias) or direct.get(alias.replace(".SA", ""))
                    if fallback and _payload_matches_cache_key(fallback, alias, valid_symbols):
                        merged[alias] = fallback
                        merged[alias.replace(".SA", "")] = fallback
                        break
            return {
                key: payload
                for key, payload in merged.items()
                if isinstance(payload, dict) and _payload_matches_cache_key(payload, key, valid_symbols)
            }
    except Exception:
        pass
    return direct


def load_public_chart_rows(aliases: list[str], interval: str, scope: str = "public_market_live") -> list[dict]:
    for alias in aliases:
        try:
            cached = get_cached_chart_data(alias, interval)
            if cached:
                record_cache_access("chart", True, scope)
                return cached
            stale_cached = get_cached_chart_data(alias, interval, allow_stale=True)
            if stale_cached:
                record_cache_access("chart_stale", True, scope)
                return stale_cached
        except Exception:
            pass

        direct_cached = _direct_cached_chart_data(alias, interval, allow_stale=True)
        if direct_cached:
            record_cache_access("chart_direct", True, scope)
            return direct_cached

    record_cache_access("chart", False, scope)
    return []
