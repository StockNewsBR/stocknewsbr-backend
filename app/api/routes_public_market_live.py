import math
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from app.engine.signal_engine import build_chart_signal_payload
from app.market.market_data_loader import (
    get_display_symbol,
)
from app.services.chart_overlay_service import build_chart_overlays
from app.services.public_ai_tools_service import build_public_ai_tools_payload
from app.services.public_market_data_service import (
    cached_price_payloads,
    load_public_chart_rows,
)
from app.services.public_news_service import build_public_news_payload
from app.services.quote_service import classify_quote_payload, is_usable_quote_payload
from app.system.system_metrics import record_cache_access


router = APIRouter(prefix="/public", tags=["Public Market Live"])
_PUBLIC_MARKET_BLOCKED_SYMBOLS = {
    "BRFS3",
    "BRFS3.SA",
    "ENBR3",
    "ENBR3.SA",
    "JBSS3",
    "JBSS3.SA",
}

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


def _is_b3_mini_future_symbol(symbol: str) -> bool:
    raw = _normalize_public_symbol(symbol)
    compact = raw[:-3] if raw.endswith(".SA") else raw
    return _B3_MINI_FUTURE_RE.match(compact) is not None


def _normalize_public_symbol(symbol: str) -> str:
    return str(symbol or "").upper().strip()


def _dedupe_public_symbols(symbols) -> list[str]:
    seen = set()
    result = []
    for symbol in symbols:
        value = _normalize_public_symbol(symbol)
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _response_symbol(symbol: str) -> str:
    value = get_display_symbol(_normalize_public_symbol(symbol))
    if value.endswith(".SA"):
        value = value[:-3]
    if value.endswith("-USD"):
        value = value.replace("-USD", "USD")
    if value.endswith("USDT"):
        value = f"{value[:-4]}USD"
    return value


def _symbol_aliases(symbol: str) -> list[str]:
    raw = _normalize_public_symbol(symbol)
    if not raw:
        return []

    display = get_display_symbol(raw)
    aliases = [raw, display]
    for candidate in list(aliases):
        base = candidate[:-3] if candidate.endswith(".SA") else candidate
        compact = base.replace("-USD", "USD")
        if compact.endswith("USDT"):
            compact = f"{compact[:-4]}USD"

        aliases.extend([base, compact])
        if compact in _CME_FUTURES_PROVIDER_SYMBOLS:
            aliases.append(_CME_FUTURES_PROVIDER_SYMBOLS[compact])
        if _B3_MINI_FUTURE_RE.match(compact):
            aliases.append(f"{compact}.SA")
        if compact.endswith("USD"):
            aliases.extend([compact.replace("USD", "-USD"), compact.replace("USD", "USDT")])
        if re.match(r"^[A-Z]{4}(3|4|5|6|11)$", base) or re.match(r"^[A-Z]{4,5}34$", base):
            aliases.append(f"{base}.SA")

    return _dedupe_public_symbols(aliases)


def _is_blocked_public_symbol(symbol: str) -> bool:
    return any(alias in _PUBLIC_MARKET_BLOCKED_SYMBOLS for alias in _symbol_aliases(symbol))


def _numeric_close_values(ohlc):
    closes = []
    for row in ohlc or []:
        try:
            close = float(row.get("close") or 0)
        except (TypeError, ValueError):
            continue
        if close > 0:
            closes.append(close)
    return closes


def _safe_float(value, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _has_usable_quote_payload(payload) -> bool:
    return is_usable_quote_payload(payload)


def _is_quote_fallback_chart(ohlc) -> bool:
    return bool(ohlc) and all(row.get("source") == "quote_cache_fallback" for row in ohlc or [])


def _compute_rsi(closes, period: int = 14):
    if len(closes) <= period:
        return None

    gains = []
    losses = []
    for previous, current in zip(closes[-period - 1 : -1], closes[-period:]):
        delta = current - previous
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def _fallback_bias(closes):
    if len(closes) < 2:
        return "neutro"

    latest = closes[-1]
    first = closes[0]
    short_window = closes[-min(len(closes), 8) :]
    short_avg = sum(short_window) / len(short_window)
    if latest >= short_avg and latest >= first:
        return "alta"
    if latest < short_avg and latest < first:
        return "baixa"
    return "neutro"


def _fallback_score(closes, rsi):
    if not closes:
        return None
    bias = _fallback_bias(closes)
    base = 5.0
    if rsi is not None:
        base += (float(rsi) - 50) / 12
    if bias == "alta":
        base += 1.0
    elif bias == "baixa":
        base -= 1.0
    return round(max(1.0, min(10.0, base)), 1)


def _resolve_cached_quote(cached_payloads, symbol: str):
    for alias in _symbol_aliases(symbol):
        candidate = cached_payloads.get(alias)
        if not isinstance(candidate, dict):
            continue
        if _has_usable_quote_payload(candidate):
            payload = {**candidate, "symbol": _response_symbol(symbol)}
            if payload.get("source") is None:
                payload = {**payload, "source": "market_cache"}
            payload["quote_status"] = classify_quote_payload(payload)
            return payload

    return {
        "symbol": _response_symbol(symbol),
        "price": None,
        "change": None,
        "change_pct": None,
        "volume": None,
        "high": None,
        "low": None,
        "source": "empty",
        "quote_status": "empty",
        "stale": False,
    }


def _resolve_quote_for_chart(symbol: str):
    aliases = _symbol_aliases(symbol)
    if not aliases:
        return None

    cached_payloads = cached_price_payloads(aliases)
    if not any(_has_usable_quote_payload(cached_payloads.get(alias)) for alias in aliases):
        stale_payloads = cached_price_payloads(aliases, allow_stale=True)
        for alias, payload in stale_payloads.items():
            if not _has_usable_quote_payload(cached_payloads.get(alias)):
                cached_payloads[alias] = payload

    for alias in aliases:
        payload = cached_payloads.get(alias)
        if not isinstance(payload, dict):
            continue
        price = _safe_float(payload.get("price"))
        if price > 0:
            return {**payload, "symbol": _response_symbol(symbol)}

    for payload in cached_payloads.values():
        if isinstance(payload, dict) and _safe_float(payload.get("price")) > 0:
            return {**payload, "symbol": _response_symbol(symbol)}

    return None


def _interval_shape(interval: str) -> tuple[int, timedelta]:
    normalized = str(interval or "1D").upper().strip()
    if normalized == "1D":
        return 78, timedelta(minutes=5)
    if normalized == "1W":
        return 7, timedelta(days=1)
    if normalized == "1M":
        return 22, timedelta(days=1)
    if normalized == "3M":
        return 63, timedelta(days=1)
    if normalized == "6M":
        return 90, timedelta(days=2)
    if normalized == "YTD":
        return 120, timedelta(days=1)
    if normalized == "1Y":
        return 122, timedelta(days=3)
    return 156, timedelta(days=7)


def _normalize_chart_interval(interval: str | None = "1D", range_value: str | None = None) -> str:
    raw_range = range_value if isinstance(range_value, str) else None
    raw_interval = interval if isinstance(interval, str) else None
    return str(raw_range or raw_interval or "1D").upper().strip()


def _build_quote_fallback_chart(symbol: str, interval: str):
    quote = _resolve_quote_for_chart(symbol)
    if not quote:
        return []

    price = _safe_float(quote.get("price"))
    if price <= 0:
        return []

    change = _safe_float(quote.get("change"))
    change_pct = _safe_float(quote.get("change_pct"))
    previous = price - change if change else 0.0
    if previous <= 0 and change_pct:
        previous = price / max(0.05, 1 + (change_pct / 100))
    if previous <= 0:
        direction = 1 if change_pct >= 0 else -1
        previous = price * (1 - direction * max(abs(change_pct), 0.08) / 100)

    count, step = _interval_shape(interval)
    volume = max(_safe_float(quote.get("volume")), 0.0)
    high_quote = _safe_float(quote.get("high"))
    low_quote = _safe_float(quote.get("low"))
    amplitude = max(abs(price - previous), price * 0.003)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = []
    last_close = previous

    for index in range(count):
        progress = index / max(count - 1, 1)
        trend = previous + ((price - previous) * progress)
        wave = math.sin(progress * math.pi * 4.0) * amplitude * 0.34
        close = price if index == count - 1 else max(0.01, trend + wave)
        open_price = last_close if index else max(0.01, close - ((price - previous) / max(count, 1)))
        spread = max(abs(close - open_price), price * 0.0012)
        high = max(open_price, close) + spread * 0.85
        low = max(0.01, min(open_price, close) - spread * 0.85)

        if index == count - 1:
            high = max(high, high_quote if high_quote > 0 else high, close)
            low = min(low, low_quote if low_quote > 0 else low, close)

        timestamp = now - step * (count - index - 1)
        rows.append(
            {
                "time": timestamp.isoformat(),
                "open": round(open_price, 6),
                "high": round(high, 6),
                "low": round(low, 6),
                "close": round(close, 6),
                "volume": round(volume / max(count, 1), 2),
                "source": "quote_cache_fallback",
            }
        )
        last_close = close

    return rows


@router.get("/market/quotes")
def public_quotes(symbols: str = Query(default="")):
    tickers = _dedupe_public_symbols(
        _normalize_public_symbol(part)
        for part in symbols.split(",")
        if part.strip() and not _is_blocked_public_symbol(part)
    )
    limited_tickers = tickers[:80]
    cache_keys = _dedupe_public_symbols(
        alias for symbol in limited_tickers for alias in _symbol_aliases(symbol)
    )
    cached_payloads = cached_price_payloads(cache_keys)
    missing_tickers = [
        symbol
        for symbol in limited_tickers
        if not any(_has_usable_quote_payload(cached_payloads.get(alias)) for alias in _symbol_aliases(symbol))
    ]
    if missing_tickers:
        still_missing = [
            symbol
            for symbol in missing_tickers
            if not any(_has_usable_quote_payload(cached_payloads.get(alias)) for alias in _symbol_aliases(symbol))
        ]
        if still_missing:
            stale_keys = _dedupe_public_symbols(
                alias for symbol in still_missing for alias in _symbol_aliases(symbol)
            )
            stale_payloads = cached_price_payloads(stale_keys, allow_stale=True)
            for key, payload in stale_payloads.items():
                if not _has_usable_quote_payload(cached_payloads.get(key)):
                    cached_payloads[key] = payload

    for symbol in limited_tickers:
        record_cache_access(
            "quote",
            any(_has_usable_quote_payload(cached_payloads.get(alias)) for alias in _symbol_aliases(symbol)),
            "public_quotes",
        )

    items = [_resolve_cached_quote(cached_payloads, symbol) for symbol in limited_tickers]
    return {"items": items, "count": len(items)}


@router.get("/market/insight/{symbol}")
def public_market_insight(symbol: str, interval: str = "1D"):
    ticker = _normalize_public_symbol(symbol)
    response_symbol = _response_symbol(ticker)
    if _is_blocked_public_symbol(ticker):
        return {
            "symbol": response_symbol,
            "score": None,
            "rsi": None,
            "trend_bias": None,
            "signal": None,
            "summary": {"source": "blocked_symbol"},
    }
    ohlc = _load_chart_data_fast(ticker, interval)
    empty_reason = "b3_future_exact_chart_unavailable" if _is_b3_mini_future_symbol(ticker) else "empty_chart"
    if not ohlc:
        return {
            "symbol": response_symbol,
            "score": None,
            "rsi": None,
            "trend_bias": None,
            "signal": None,
            "summary": {
                "ticker": response_symbol,
                "source": empty_reason,
                "fallback": True,
                "status": "empty",
                "provider_status": empty_reason,
            },
            "fallback": True,
            "status": "empty",
            "provider_status": empty_reason,
        }

    is_quote_fallback = _is_quote_fallback_chart(ohlc)
    insight = {} if is_quote_fallback else (build_chart_signal_payload(ticker, ohlc, interval=interval) or {})
    summary = dict(insight.get("summary") or {})
    if is_quote_fallback:
        summary.update({"source": "quote_cache_fallback", "fallback": True, "confidence": "derived"})
    closes = _numeric_close_values(ohlc)
    rsi = insight.get("rsi")
    if rsi is None:
        rsi = _compute_rsi(closes)
    trend_bias = summary.get("trend_bias") or insight.get("trend_bias") or _fallback_bias(closes)
    score = insight.get("score")
    if score is None:
        score = _fallback_score(closes, rsi)

    return {
        "symbol": response_symbol,
        "score": score,
        "rsi": rsi,
        "trend_bias": trend_bias,
        "signal": insight.get("signal") or trend_bias,
        "summary": summary,
    }


@router.get("/market/chart/{symbol}")
def public_market_chart(
    symbol: str,
    interval: str = "1D",
    range_value: str | None = Query(default=None, alias="range"),
):
    ticker = _normalize_public_symbol(symbol)
    response_symbol = _response_symbol(ticker)
    chart_interval = _normalize_chart_interval(interval, range_value)
    if _is_blocked_public_symbol(ticker):
        return _empty_chart_payload(response_symbol, chart_interval, "blocked_symbol")
    ohlc = _load_chart_data_fast(ticker, chart_interval)
    if not ohlc:
        reason = "b3_future_exact_chart_unavailable" if _is_b3_mini_future_symbol(ticker) else "empty_chart"
        return _empty_chart_payload(response_symbol, chart_interval, reason)

    is_quote_fallback = _is_quote_fallback_chart(ohlc)
    signals = []
    chart_signal = {} if is_quote_fallback else (build_chart_signal_payload(ticker, ohlc, interval=chart_interval) or {})
    if chart_signal:
        signals.append(chart_signal)

    overlays = build_chart_overlays(ticker, ohlc, signals, interval=chart_interval)
    summary = dict(overlays["summary"] or {})
    if is_quote_fallback:
        summary.update({"source": "quote_cache_fallback", "fallback": True, "confidence": "derived"})
    return {
        "ticker": response_symbol,
        "interval": chart_interval,
        "ohlc": ohlc,
        "series": overlays["series"],
        "markers": overlays["markers"],
        "zones": overlays["zones"],
        "summary": summary,
    }


@router.get("/market/bundle/{symbol}")
def public_market_bundle(
    symbol: str,
    interval: str = "1D",
    limit: int = 6,
    range_value: str | None = Query(default=None, alias="range"),
):
    chart_interval = _normalize_chart_interval(interval, range_value)
    safe_limit = max(1, min(int(limit or 6), 20))
    ticker = _normalize_public_symbol(symbol)
    response_symbol = _response_symbol(ticker)
    cached_payloads = cached_price_payloads(_symbol_aliases(ticker), allow_stale=True)
    quote = _resolve_cached_quote(cached_payloads, ticker)
    record_cache_access("quote", _has_usable_quote_payload(quote), "public_bundle")

    return {
        "symbol": response_symbol,
        "quote": quote,
        "insight": public_market_insight(ticker, interval=chart_interval),
        "chart": public_market_chart(ticker, interval=chart_interval, range_value=None),
        "news": build_public_news_payload(response_symbol, limit=safe_limit, source="public_bundle", allow_fetch=False),
        "ai_tools": build_public_ai_tools_payload(),
        "source": "cache_snapshot_bundle",
    }


def _empty_chart_payload(symbol: str, interval: str, reason: str):
    return {
        "ticker": symbol,
        "interval": interval,
        "ohlc": [],
        "series": [],
        "markers": [],
        "zones": [],
        "summary": {
            "ticker": symbol,
            "source": reason,
            "fallback": True,
            "status": "empty",
            "provider_status": reason,
        },
        "fallback": True,
        "status": "empty",
        "provider_status": reason,
    }


def _load_chart_data_fast(ticker: str, interval: str):
    rows = load_public_chart_rows(_symbol_aliases(ticker), interval)
    if rows:
        return rows
    cache_key = "chart_exact_miss_b3_future" if _is_b3_mini_future_symbol(ticker) else "chart_exact_miss"
    record_cache_access(cache_key, False, "public_market_live")
    return []
