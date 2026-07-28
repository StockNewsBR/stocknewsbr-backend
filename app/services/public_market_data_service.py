from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

from app.engine.indicators.vector_indicator_engine import RSI_PERIOD, compute_latest_rsi
from app.market.market_data_loader import (
    get_cached_chart_data,
    get_cached_price_snapshots,
)
from app.market.universe_registry import INDEX_UNIVERSE
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
_QUOTE_DIRECT_MAX_AGE_SECONDS = 300
_QUOTE_RETENTION_SECONDS = 60 * 60 * 24 * 7
_CHART_DIRECT_MAX_AGE_SECONDS = 60 * 60 * 24 * 14
_CHART_RETENTION_SECONDS = 60 * 60 * 24 * 14
_PUBLIC_RSI_SOURCE = "canonical_indicator_engine"
_CHART_LEVEL_SOURCE = "chart_overlay"
_CHART_LEVEL_ALGORITHM_VERSION = "recent_extrema_v1"
_LEVEL_MIN_SIDE_PCT = float(os.getenv("LEVEL_MIN_SIDE_PCT", "0.0015"))
_LEVEL_MIN_WIDTH_PCT = float(os.getenv("LEVEL_MIN_WIDTH_PCT", "0.0035"))
_LEVEL_MIN_TOUCHES = max(2, int(os.getenv("LEVEL_MIN_TOUCHES", "2")))
# ponytail: calendar grace covers weekends; use an exchange calendar if holiday precision becomes operational.
_DAILY_MAX_SESSION_LAG_DAYS = 3
INDEX_SPARK_INTERVAL = "3M"
INDEX_SPARK_MAX_POINTS = 60


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


def _finite_number(value) -> float | None:
    """Like _finite_positive but keeps negatives: change/change_pct go both ways."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _context_symbol(symbol: str) -> str:
    normalized = canonical_symbol(symbol)
    if normalized:
        return normalized
    return str(symbol or "").upper().strip()


def _context_timeframe(timeframe: str) -> str:
    label = str(timeframe or "1D").upper().strip() or "1D"
    # "@5M" is a candle-size request, not a range: publish it in candle form ("5m")
    # so the metadata never says "1D" while the candles are five minutes wide.
    return label[1:].lower() if label.startswith("@") else label


def _row_as_of(row: dict | None) -> str | None:
    if not isinstance(row, dict):
        return None
    for key in ("time", "timestamp", "datetime", "as_of"):
        value = row.get(key)
        if value in (None, ""):
            continue
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except (TypeError, ValueError):
                pass
        return str(value)
    return None


def public_chart_as_of(rows: list[dict] | None) -> str | None:
    for row in reversed(rows or []):
        as_of = _row_as_of(row)
        if as_of is not None:
            return as_of
    return None


def public_daily_freshness_status(
    rows: list[dict] | None,
    session_date: object,
    *,
    required_count: int = RSI_PERIOD + 1,
) -> str:
    """Classify daily candles against the selected quote session."""
    closes = _valid_chart_closes(rows)
    if len(closes) < required_count:
        return "PENDING" if not rows else "INSUFFICIENT_DATA"
    if not session_date:
        return "READY"
    as_of = public_chart_as_of(rows)
    try:
        candle_date = datetime.fromisoformat(str(as_of)[:10]).date()
        quote_date = datetime.fromisoformat(str(session_date)[:10]).date()
    except (TypeError, ValueError):
        return "STALE"
    lag_days = (quote_date - candle_date).days
    return "READY" if 0 <= lag_days <= _DAILY_MAX_SESSION_LAG_DAYS else "STALE"


def public_daily_age_sessions(
    rows: list[dict] | None,
    session_date: object,
    *,
    continuous_market: bool = False,
) -> int | None:
    """Count elapsed market sessions after the latest daily candle."""
    as_of = public_chart_as_of(rows)
    if not as_of or not session_date:
        return None
    try:
        candle_date = datetime.fromisoformat(str(as_of)[:10]).date()
        quote_date = datetime.fromisoformat(str(session_date)[:10]).date()
    except (TypeError, ValueError):
        return None
    if quote_date < candle_date:
        return None
    if continuous_market:
        return (quote_date - candle_date).days
    return sum(
        1
        for offset in range(1, (quote_date - candle_date).days + 1)
        if (candle_date + timedelta(days=offset)).weekday() < 5
    )


def build_crypto_intraday_rvol_contract(
    symbol: str,
    rows: list[dict] | None,
    *,
    lookback_days: int = 20,
    minimum_samples: int = 7,
) -> dict:
    """Compare a 5m crypto bucket with the same UTC bucket on prior days.

    Crypto trades continuously, so an exchange-session or weekday split would
    silently apply equity semantics. Each prior UTC date contributes at most
    one positive-volume sample and the baseline is the median.
    """
    canonical = _context_symbol(symbol)
    base = {
        "symbol": canonical,
        "current_volume": None,
        "current_bucket_volume": None,
        "average_volume_comparable": None,
        "rvol_ratio": None,
        "rvol_percent": None,
        "label": "RVOL intraday indisponível",
        "status": "INSUFFICIENT_DATA",
        "method": "same_utc_bucket_median",
        "baseline": "same_utc_bucket_median",
        "timeframe": "5m",
        "window_days": max(1, int(lookback_days or 20)),
        "minimum_sample_count": max(1, int(minimum_samples or 7)),
        "sample_count": 0,
        "weekday_split": False,
        "operational_ready": False,
        "reason": "no_5m_candles",
        "as_of": None,
        "source": "chart_cache",
    }

    parsed: list[tuple[datetime, float]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        raw_time = _row_as_of(row)
        volume = _finite_positive(row.get("volume"))
        if not raw_time:
            continue
        try:
            stamp = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
            stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
        # Keep zero-volume current buckets visible as insufficient instead of
        # silently falling back to an earlier, completed bucket.
        parsed.append((stamp, float(volume or 0.0)))

    if not parsed:
        return base

    parsed.sort(key=lambda item: item[0])
    current_at, current_volume = parsed[-1]
    base.update({
        "current_volume": current_volume if current_volume > 0 else None,
        "current_bucket_volume": current_volume if current_volume > 0 else None,
        "as_of": current_at.isoformat(),
        "current_bucket_utc": f"{current_at.hour:02d}:{(current_at.minute // 5) * 5:02d}",
    })
    if current_volume <= 0:
        base["reason"] = "current_bucket_volume_unavailable"
        return base

    current_bucket = (current_at.hour, current_at.minute // 5)
    samples_by_date: dict[object, float] = {}
    for stamp, volume in parsed[:-1]:
        age_days = (current_at.date() - stamp.date()).days
        if not 1 <= age_days <= base["window_days"]:
            continue
        if (stamp.hour, stamp.minute // 5) != current_bucket or volume <= 0:
            continue
        samples_by_date[stamp.date()] = volume

    samples = list(samples_by_date.values())
    base["sample_count"] = len(samples)
    if len(samples) < base["minimum_sample_count"]:
        base["reason"] = "insufficient_same_utc_bucket_samples"
        return base

    comparable_median = float(median(samples))
    if comparable_median <= 0:
        base["reason"] = "invalid_same_utc_bucket_baseline"
        return base

    ratio = current_volume / comparable_median
    label = "Abaixo da média" if ratio < 0.70 else "Na média" if ratio < 1.30 else "Acima da média"
    base.update({
        "average_volume_comparable": round(comparable_median, 6),
        "rvol_ratio": round(ratio, 4),
        "rvol_percent": round(ratio * 100, 1),
        "label": label,
        "status": "READY",
        "operational_ready": True,
        "reason": None,
    })
    return base


def _valid_chart_closes(rows: list[dict] | None) -> list[float]:
    closes: list[float] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        close = _finite_positive(row.get("close"))
        if close is not None:
            closes.append(close)
    return closes


def _rsi_as_of(rows: list[dict] | None) -> str | None:
    for row in reversed(rows or []):
        if not isinstance(row, dict) or _finite_positive(row.get("close")) is None:
            continue
        return _row_as_of(row)
    return None


_CANDLE_INTERVAL_STEPS = (
    (60, "1m"),
    (300, "5m"),
    (900, "15m"),
    (1800, "30m"),
    (3600, "1h"),
    (14400, "4h"),
    (86400, "1d"),
    (604800, "1wk"),
)


def _candle_interval(rows: list[dict] | None) -> str | None:
    """Real spacing between the candles the RSI was computed on.

    The route's `interval` is a *range* label, not a candle size: "1D" means one
    day of 5m candles, "1M" means one month of 1d candles. Publishing only the
    range makes the UI render an intraday RSI as "RSI D1".
    """
    stamps: list[float] = []
    for row in rows or []:
        raw = _row_as_of(row) if isinstance(row, dict) else None
        if not raw:
            continue
        try:
            stamps.append(datetime.fromisoformat(str(raw)).timestamp())
        except (TypeError, ValueError, OverflowError, OSError):
            return None
    deltas = sorted(later - earlier for earlier, later in zip(stamps, stamps[1:]) if later > earlier)
    if not deltas:
        return None
    median = deltas[len(deltas) // 2]
    return min(_CANDLE_INTERVAL_STEPS, key=lambda step: abs(step[0] - median))[1]


def _is_quote_fallback_chart(rows: list[dict] | None) -> bool:
    return bool(rows) and all(
        isinstance(row, dict) and str(row.get("source") or "").lower().strip() == "quote_cache_fallback"
        for row in rows or []
    )


def build_public_rsi_contract(
    symbol: str,
    timeframe: str,
    rows: list[dict] | None,
    *,
    empty_status: str = "INSUFFICIENT_DATA",
    empty_reason: str | None = None,
    period: int = RSI_PERIOD,
) -> dict:
    normalized_period = int(period) if isinstance(period, int) and period > 0 else RSI_PERIOD
    required_count = normalized_period + 1
    closes = _valid_chart_closes(rows)
    candle_count = len(closes)
    # The RSI is computed on these rows, so the timeframe it is published under must be
    # the real spacing of these rows -- never the range label that produced them. Only
    # when there are no candles to measure does the requested label stand in.
    candle_interval = _candle_interval(rows)
    metadata = {
        "symbol": _context_symbol(symbol),
        "timeframe": candle_interval or _context_timeframe(timeframe),
        "candle_interval": candle_interval,
        "period": normalized_period,
        "as_of": _rsi_as_of(rows),
        "source": _PUBLIC_RSI_SOURCE,
        "candle_count": candle_count,
        "required_count": required_count,
        "status": "INSUFFICIENT_DATA",
        "reason": "insufficient_candles",
    }

    if _is_quote_fallback_chart(rows):
        metadata["reason"] = "non_canonical_chart_source"
        return {"rsi": None, "rsi_metadata": metadata}
    if candle_count == 0:
        metadata["status"] = str(empty_status or "INSUFFICIENT_DATA").upper()
        metadata["reason"] = empty_reason or "no_candles"
        return {"rsi": None, "rsi_metadata": metadata}
    if candle_count < required_count:
        return {"rsi": None, "rsi_metadata": metadata}

    rsi = compute_latest_rsi(closes, period=normalized_period)
    if rsi is None:
        metadata["reason"] = "calculation_unavailable"
        return {"rsi": None, "rsi_metadata": metadata}

    metadata["status"] = "AVAILABLE"
    metadata["reason"] = None
    return {"rsi": round(float(rsi), 4), "rsi_metadata": metadata}


def _chart_level_kind(zone: dict) -> str | None:
    explicit = str(zone.get("kind") or "").lower().strip()
    if explicit in {"support", "resistance"}:
        return explicit
    label = str(zone.get("label") or "").lower().strip()
    if "support" in label or "suport" in label:
        return "support"
    if "resist" in label:
        return "resistance"
    return None


def normalize_public_chart_zones(
    zones: list[dict] | None,
    *,
    symbol: str,
    timeframe: str,
    rows: list[dict] | None,
) -> list[dict]:
    if _is_quote_fallback_chart(rows):
        return []

    normalized_symbol = _context_symbol(symbol)
    normalized_timeframe = _context_timeframe(timeframe)
    as_of = public_chart_as_of(rows)
    rows_stale = any(
        isinstance(row, dict)
        and (row.get("stale") is True or "stale" in str(row.get("source") or "").lower())
        for row in rows or []
    )
    seen_prices: set[float] = set()
    seen_kinds: set[str] = set()
    normalized: list[dict] = []

    for zone in zones or []:
        if not isinstance(zone, dict):
            continue
        kind = _chart_level_kind(zone)
        price = _finite_positive(zone.get("price"))
        if kind is not None and price is None:
            continue
        price_key = round(price, 10) if price is not None else None
        if price_key is not None and price_key in seen_prices:
            continue
        if kind is not None and kind in seen_kinds:
            continue

        item = dict(zone)
        item.update({
            "symbol": normalized_symbol,
            "timeframe": normalized_timeframe,
            "as_of": as_of,
            "source": zone.get("source") or _CHART_LEVEL_SOURCE,
            "algorithm_version": zone.get("algorithm_version") or _CHART_LEVEL_ALGORITHM_VERSION,
            "stale": bool(zone.get("stale")) or rows_stale,
        })
        if price is not None:
            item["price"] = price
        if kind is not None:
            item["kind"] = kind
            seen_kinds.add(kind)
        if price_key is not None:
            seen_prices.add(price_key)
        normalized.append(item)

    latest_close = _finite_positive((rows or [{}])[-1].get("close") if rows else None)
    support = next((item for item in normalized if item.get("kind") == "support"), None)
    resistance = next((item for item in normalized if item.get("kind") == "resistance"), None)
    if not (latest_close and support and resistance):
        return normalized

    ranges = []
    for row in (rows or [])[-14:]:
        high, low = _finite_positive(row.get("high")), _finite_positive(row.get("low"))
        if high is not None and low is not None and high >= low:
            ranges.append(high - low)
    atr14 = sum(ranges) / len(ranges) if len(ranges) >= 14 else None
    support_price, resistance_price = support["price"], resistance["price"]
    min_side = max(latest_close * _LEVEL_MIN_SIDE_PCT, (atr14 or 0) * 0.25)
    min_width = max(latest_close * _LEVEL_MIN_WIDTH_PCT, (atr14 or 0) * 0.75)
    touch_tolerance = max(latest_close * 0.001, (atr14 or 0) * 0.10)
    support_touches = sum(1 for row in rows or [] if (low := _finite_positive(row.get("low"))) is not None and abs(low - support_price) <= touch_tolerance)
    resistance_touches = sum(1 for row in rows or [] if (high := _finite_positive(row.get("high"))) is not None and abs(high - resistance_price) <= touch_tolerance)
    valid = (
        atr14 is not None
        and support_touches >= _LEVEL_MIN_TOUCHES
        and resistance_touches >= _LEVEL_MIN_TOUCHES
        and support_price < latest_close < resistance_price
        and latest_close - support_price >= min_side
        and resistance_price - latest_close >= min_side
        and resistance_price - support_price >= min_width
    )
    for item, touches in ((support, support_touches), (resistance, resistance_touches)):
        item.update({
            "status": "READY" if valid else "INSUFFICIENT_SEPARATION",
            "operational": valid,
            "distance_pct": abs(item["price"] - latest_close) / latest_close * 100,
            "atr14": atr14,
            "distance_atr": abs(item["price"] - latest_close) / atr14 if atr14 else None,
            "strength_score": min(100, touches * 35 + 20) if valid else None,
            "touches": touches,
            "rejections": touches - 1 if touches > 1 else 0,
        })
        if not valid:
            item["micro_timeframe"] = normalized_timeframe
            item["reason"] = "nearest_pivots_form_micro_range"
    return normalized


def _fresh_enough(entry: dict, allow_stale: bool, max_age_seconds: int, retention_seconds: int = None) -> bool:
    timestamp = _finite_positive(entry.get("timestamp"))
    if timestamp is None:
        return False
    age = time.time() - timestamp
    if age < 0:
        return False
    if retention_seconds is not None and age > retention_seconds:
        return False
    if age <= max_age_seconds:
        return True
    return allow_stale


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
            if not isinstance(entry, dict) or not _fresh_enough(entry, allow_stale, _QUOTE_DIRECT_MAX_AGE_SECONDS, _QUOTE_RETENTION_SECONDS):
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
        if not isinstance(entry, dict) or not _fresh_enough(entry, allow_stale, _CHART_DIRECT_MAX_AGE_SECONDS, _CHART_RETENTION_SECONDS):
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


def schedule_quote_warmup(symbol: str) -> bool:
    """Async escape hatch for a cache miss on a valid symbol.

    HTTP surfaces stay cache-only (no inline provider call); this only enqueues a
    background warmup, mirroring how public news schedules its own warmup.
    """
    try:
        from app.system.quote_warmup import request_on_demand_quote_warmup

        return bool(request_on_demand_quote_warmup(symbol))
    except Exception:
        return False


def _cached_index_quote(provider_symbol: str) -> dict:
    aliases = _symbol_aliases(provider_symbol)
    best = {}
    for payload in cached_price_payloads(aliases, allow_stale=True).values():
        if isinstance(payload, dict):
            if _finite_positive(payload.get("price")) is not None:
                return payload
            if not best:
                best = payload
    return best


def build_public_indices_payload() -> dict:
    """Cache-only index strip; the quote/chart warmup keeps these symbols warm."""
    items = []
    for symbol, provider, display_name, currency in INDEX_UNIVERSE:
        quote = _cached_index_quote(provider)
        rows = load_public_chart_rows(_symbol_aliases(provider), INDEX_SPARK_INTERVAL, scope="public_indices")
        spark_closes = _valid_chart_closes(rows)[-INDEX_SPARK_MAX_POINTS:]

        price = _finite_positive(quote.get("price"))
        prev_close = _finite_positive(quote.get("previous_close"))
        change = _finite_number(quote.get("change"))
        change_pct = _finite_number(quote.get("change_pct"))

        if price is None and spark_closes:
            price = spark_closes[-1]
            if len(spark_closes) > 1:
                prev_close = prev_close or spark_closes[-2]
                if prev_close and prev_close > 0:
                    change = round(price - prev_close, 4)
                    change_pct = round(((price - prev_close) / prev_close) * 100, 2)

        items.append({
            "symbol": symbol,
            "display_name": display_name,
            "price": price,
            "change": change,
            "change_pct": change_pct,
            # Same baseline contract as the quote surfaces: the producer already
            # measures against the previous SESSION close, so the strip only has
            # to publish it for auditability.
            "previous_close": prev_close,
            "quote_time": quote.get("quote_time") or None,
            "market_state": quote.get("market_state") or None,
            "spark": spark_closes,
            "currency": currency,
            "status": "valid" if price is not None else "empty",
        })
    return {"items": items, "count": len(items)}


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
