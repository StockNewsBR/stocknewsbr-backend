# =====================================================
# MARKET DATA LOADER
# =====================================================

from __future__ import annotations

import logging
import json
import math
import os
import re
from pathlib import Path
from threading import RLock, get_ident
import time
from typing import List, Optional

from app.system.system_metrics import (
    current_provider_call_source,
    record_cache_lookup,
    record_external_provider_call,
    record_worker_stage_duration,
)

logger = logging.getLogger("stocknewsbr.market_data_loader")
_YFINANCE = None
_PRICE_CACHE_TTL_SECONDS = 15 * 60
_CHART_CACHE_TTL_SECONDS = 300
_PRICE_CACHE_FILE = Path("runtime/cache/market_quotes.json")
_PRICE_SNAPSHOT_CACHE = {}
_CHART_DATA_CACHE = {}
_SYMBOL_FAILURES = {}
_PRICE_SNAPSHOT_CACHE_LOCK = RLock()
_PRICE_CACHE_LOADED = False
_PRICE_CACHE_MTIME = 0.0
_PRICE_CACHE_INCLUDE_STALE = False
_SYMBOL_FAILURE_COOLDOWN_SECONDS = 180
_PERMANENT_PROVIDER_BLOCKLIST = {
    "BRFS3",
    "BRFS3.SA",
    "ENBR3",
    "ENBR3.SA",
    "JBSS3",
    "JBSS3.SA",
}

_CRYPTO_YF_SYMBOLS = {
    "BTCUSD": "BTC-USD",
    "BTCUSDT": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "ETHUSDT": "ETH-USD",
    "BNBUSD": "BNB-USD",
    "BNBUSDT": "BNB-USD",
    "SOLUSD": "SOL-USD",
    "SOLUSDT": "SOL-USD",
    "XRPUSD": "XRP-USD",
    "XRPUSDT": "XRP-USD",
    "ADAUSD": "ADA-USD",
    "ADAUSDT": "ADA-USD",
    "AVAXUSD": "AVAX-USD",
    "AVAXUSDT": "AVAX-USD",
    "DOGEUSD": "DOGE-USD",
    "DOGEUSDT": "DOGE-USD",
    "LINKUSD": "LINK-USD",
    "LINKUSDT": "LINK-USD",
    "MATICUSD": "MATIC-USD",
    "MATICUSDT": "MATIC-USD",
}


def _has_real_price_payload(payload: Optional[dict]) -> bool:
    if not isinstance(payload, dict):
        return False
    try:
        price = float(payload.get("price"))
    except (TypeError, ValueError):
        return False
    return math.isfinite(price) and price > 0


def _requires_provider_identity(symbol: str) -> bool:
    original = (symbol or "").upper().strip()
    normalized = _normalize_symbol(original)
    return (
        original in _CME_FUTURES_PROVIDER_SYMBOLS
        or normalized in _CME_FUTURES_DISPLAY_SYMBOLS
        or _B3_MINI_FUTURE_RE.match(original) is not None
    )


def _payload_matches_requested_symbol(symbol: str, payload: Optional[dict]) -> bool:
    if not isinstance(payload, dict):
        return False
    if _is_bdr_symbol(symbol):
        source = str(payload.get("source") or "").lower().strip()
        provider_symbol = str(payload.get("provider_symbol") or "").upper().strip()
        if source == "proxy_market":
            return False
        if not provider_symbol:
            return False

        normalized_symbol = _normalize_symbol(symbol)
        requested_display = _cache_key(symbol)
        provider_display = _normalize_ticker_display(provider_symbol, provider_symbol)
        return provider_symbol == normalized_symbol or (
            provider_symbol.endswith(".SA") and provider_display == requested_display
        )
    if not _requires_provider_identity(symbol):
        return True
    original = (symbol or "").upper().strip()
    if _B3_MINI_FUTURE_RE.match(original):
        return (
            str(payload.get("reference_proxy_for") or "").upper().strip() == original
            and str(payload.get("source") or "").lower() == "reference_proxy"
        ) or str(payload.get("provider_symbol") or "").upper().strip() == _normalize_symbol(symbol)
    return str(payload.get("provider_symbol") or "").upper().strip() == _normalize_symbol(symbol)

_CRYPTO_DISPLAY_TO_YF = {display: provider for display, provider in _CRYPTO_YF_SYMBOLS.items()}

_CME_FUTURES_PROVIDER_SYMBOLS = {
    "NQ": "NQ=F",
    "MNQ": "MNQ=F",
    "MNO": "MNQ=F",
    "ES": "ES=F",
    "MES": "MES=F",
    "YM": "YM=F",
    "MYM": "MYM=F",
}

_CME_FUTURES_DISPLAY_SYMBOLS = {
    "NQ=F": "NQ",
    "MNQ=F": "MNQ",
    "ES=F": "ES",
    "MES=F": "MES",
    "YM=F": "YM",
    "MYM=F": "MYM",
}

_B3_MINI_FUTURE_RE = re.compile(r"^(WIN|WDO)[FGHJKMNQUVXZ]\d{2}$")
_BDR_DISPLAY_RE = re.compile(r"^[A-Z0-9]{3,5}34(?:\.SA)?$")
_B3_MINI_FUTURE_REFERENCE_SYMBOLS = {
    "WIN": ("^BVSP", 1.0),
    "WDO": ("BRL=X", 1000.0),
}

_BDR_PROVIDER_SYMBOLS = {
    "AMD34": "A1MD34.SA",
    "AMD34.SA": "A1MD34.SA",
    "AMZN34": "AMZO34.SA",
    "AMZN34.SA": "AMZO34.SA",
    "AMZO34": "AMZO34.SA",
    "AMZO34.SA": "AMZO34.SA",
    "CCRO3": "MOTV3.SA",
    "CCRO3.SA": "MOTV3.SA",
    "ELET3": "AXIA3.SA",
    "ELET3.SA": "AXIA3.SA",
    "ELET6": "AXIA6.SA",
    "ELET6.SA": "AXIA6.SA",
    "INTC34": "I1NC34.SA",
    "INTC34.SA": "I1NC34.SA",
    "META34": "M1TA34.SA",
    "META34.SA": "M1TA34.SA",
    "M1TA34": "M1TA34.SA",
    "M1TA34.SA": "M1TA34.SA",
    "NTCO3": "NATU3.SA",
    "NTCO3.SA": "NATU3.SA",
    "VIIA3": "BHIA3.SA",
    "VIIA3.SA": "BHIA3.SA",
}

_BDR_PROXY_SYMBOLS = {
    "AAPL34": "AAPL",
    "AAPL34.SA": "AAPL",
    "AMZN34": "AMZN",
    "AMZN34.SA": "AMZN",
    "AMZO34": "AMZN",
    "AMZO34.SA": "AMZN",
    "AMD34": "AMD",
    "AMD34.SA": "AMD",
    "META34": "META",
    "META34.SA": "META",
    "M1TA34": "META",
    "M1TA34.SA": "META",
    "MSFT34": "MSFT",
    "MSFT34.SA": "MSFT",
    "NVDC34": "NVDA",
    "NVDC34.SA": "NVDA",
    "TSLA34": "TSLA",
    "TSLA34.SA": "TSLA",
    "GOGL34": "GOOGL",
    "GOGL34.SA": "GOOGL",
    "NFLX34": "NFLX",
    "NFLX34.SA": "NFLX",
    "INTC34": "INTC",
    "INTC34.SA": "INTC",
}


def _get_yfinance():
    global _YFINANCE
    if _YFINANCE is None:
        import yfinance as yf_module

        _YFINANCE = yf_module
    return _YFINANCE


def _network_provider_allowed() -> bool:
    return current_provider_call_source() != "http"


def _record_blocked_http_provider(symbol: str, operation: str):
    record_external_provider_call(
        "yfinance",
        f"{operation}_blocked_http",
        duration_seconds=0.0,
        success=False,
        symbol=_normalize_ticker_display(symbol, _normalize_symbol(symbol)),
        error="http_provider_blocked",
    )

_BDR_DISPLAY_SYMBOLS = {
    "A1MD34.SA": "AMD34",
    "A1MD34": "AMD34",
    "AMZN34.SA": "AMZN34",
    "AMZN34": "AMZN34",
    "AMZO34.SA": "AMZN34",
    "AMZO34": "AMZN34",
    "AXIA3.SA": "ELET3",
    "AXIA3": "ELET3",
    "AXIA6.SA": "ELET6",
    "AXIA6": "ELET6",
    "BHIA3.SA": "VIIA3",
    "BHIA3": "VIIA3",
    "I1NC34.SA": "INTC34",
    "I1NC34": "INTC34",
    "META34.SA": "META34",
    "META34": "META34",
    "M1TA34.SA": "META34",
    "M1TA34": "META34",
    "MOTV3.SA": "CCRO3",
    "MOTV3": "CCRO3",
    "NATU3.SA": "NTCO3",
    "NATU3": "NTCO3",
}


def _normalize_symbol(symbol: str) -> str:
    symbol = (symbol or "").upper().strip()

    if not symbol:
        return symbol

    if symbol in _CME_FUTURES_PROVIDER_SYMBOLS:
        return _CME_FUTURES_PROVIDER_SYMBOLS[symbol]

    if _B3_MINI_FUTURE_RE.match(symbol):
        return f"{symbol}.SA"

    if symbol in _BDR_PROVIDER_SYMBOLS:
        return _BDR_PROVIDER_SYMBOLS[symbol]

    if symbol in _CRYPTO_YF_SYMBOLS:
        return _CRYPTO_YF_SYMBOLS[symbol]

    if (
        "." not in symbol
        and "-" not in symbol
        and symbol.endswith(("3", "4", "5", "6", "11", "34"))
    ):
        return f"{symbol}.SA"

    return symbol


def _normalize_ticker_display(symbol: str, normalized_symbol: str) -> str:
    original = (symbol or "").upper().strip()

    if original in _CME_FUTURES_PROVIDER_SYMBOLS:
        return original

    if normalized_symbol in _CME_FUTURES_DISPLAY_SYMBOLS:
        return _CME_FUTURES_DISPLAY_SYMBOLS[normalized_symbol]

    if _B3_MINI_FUTURE_RE.match(original):
        return original

    if normalized_symbol in _BDR_DISPLAY_SYMBOLS:
        return _BDR_DISPLAY_SYMBOLS[normalized_symbol]

    if original in _BDR_PROVIDER_SYMBOLS:
        return original.replace(".SA", "")

    if original:
        return _BDR_DISPLAY_SYMBOLS.get(original, original.replace(".SA", ""))

    for display_symbol, provider_symbol in _CRYPTO_YF_SYMBOLS.items():
        if normalized_symbol == provider_symbol:
            return display_symbol

    return normalized_symbol.replace(".SA", "")


def _cache_key(symbol: str) -> str:
    return _normalize_ticker_display(symbol, _normalize_symbol(symbol))


def _is_bdr_symbol(symbol: str) -> bool:
    original = (symbol or "").upper().strip()
    normalized = _normalize_symbol(original)
    display = _normalize_ticker_display(original, normalized)
    return any(_BDR_DISPLAY_RE.match(value or "") is not None for value in (original, normalized, display))


def _is_permanently_blocked_symbol(symbol: str) -> bool:
    original = (symbol or "").upper().strip()
    normalized = _normalize_symbol(original)
    display = _normalize_ticker_display(original, normalized)
    return original in _PERMANENT_PROVIDER_BLOCKLIST or normalized in _PERMANENT_PROVIDER_BLOCKLIST or display in _PERMANENT_PROVIDER_BLOCKLIST


def _proxy_symbol_for(symbol: str) -> str | None:
    original = (symbol or "").upper().strip()
    normalized = _normalize_symbol(original)
    return _BDR_PROXY_SYMBOLS.get(original) or _BDR_PROXY_SYMBOLS.get(normalized)


def _b3_future_reference(symbol: str) -> tuple[str, float] | None:
    original = (symbol or "").upper().strip()
    match = _B3_MINI_FUTURE_RE.match(original)
    if not match:
        return None
    return _B3_MINI_FUTURE_REFERENCE_SYMBOLS.get(match.group(1))


def _prefer_b3_reference_proxy(symbol: str) -> bool:
    return _b3_future_reference(symbol) is not None and os.getenv("ENABLE_EXACT_B3_FUTURES_YF", "0") != "1"


def _reference_payload_for_b3_future(symbol: str) -> Optional[dict]:
    reference = _b3_future_reference(symbol)
    if not reference:
        return None

    reference_symbol, multiplier = reference
    reference_payload = _get_cached_price_payload(reference_symbol) or get_price_snapshot(reference_symbol)
    if not _has_real_price_payload(reference_payload):
        return None

    original = (symbol or "").upper().strip()
    resolved = dict(reference_payload)
    for field in ("price", "change", "high", "low"):
        try:
            value = resolved.get(field)
            if value is not None:
                resolved[field] = round(float(value) * multiplier, 4)
        except (TypeError, ValueError):
            pass

    resolved.update(
        {
            "symbol": _normalize_ticker_display(original, _normalize_symbol(original)),
            "display_symbol": _normalize_ticker_display(original, _normalize_symbol(original)),
            "provider_symbol": reference_symbol,
            "source": "reference_proxy",
            "quote_status": "reference",
            "reference_proxy_for": original,
            "reference_symbol": reference_symbol,
            "exact_contract": False,
        }
    )
    return resolved


def get_display_symbol(symbol: str) -> str:
    """Return the stable UI/cache symbol for provider aliases."""
    return _cache_key(symbol)


def _failure_key(symbol: str, provider: str = "yfinance") -> str:
    return f"{str(provider or 'unknown').lower()}:{_cache_key(symbol)}"


def _mark_symbol_failure(symbol: str, provider: str = "yfinance", error: str | None = None):
    key = _cache_key(symbol)
    if key:
        with _PRICE_SNAPSHOT_CACHE_LOCK:
            failure_key = _failure_key(symbol, provider)
            current = _SYMBOL_FAILURES.get(failure_key)
            if isinstance(current, dict):
                count = int(current.get("count", 0)) + 1
            else:
                count = 1
            _SYMBOL_FAILURES[failure_key] = {
                "timestamp": time.time(),
                "symbol": key,
                "provider": str(provider or "unknown").lower(),
                "error": str(error or "")[:240],
                "count": count,
                "last_log": float((current or {}).get("last_log", 0.0)) if isinstance(current, dict) else 0.0,
            }


def _clear_symbol_failure(symbol: str, provider: str = "yfinance"):
    key = _cache_key(symbol)
    if key:
        with _PRICE_SNAPSHOT_CACHE_LOCK:
            _SYMBOL_FAILURES.pop(_failure_key(symbol, provider), None)


def _is_symbol_cooling_down(symbol: str, provider: str = "yfinance") -> bool:
    key = _cache_key(symbol)
    if not key:
        return False
    with _PRICE_SNAPSHOT_CACHE_LOCK:
        current = _SYMBOL_FAILURES.get(_failure_key(symbol, provider))
    if not current:
        return False
    timestamp = current.get("timestamp") if isinstance(current, dict) else current
    return time.time() - float(timestamp or 0) < _SYMBOL_FAILURE_COOLDOWN_SECONDS


def _should_log_symbol_failure(symbol: str, provider: str = "yfinance") -> bool:
    now = time.time()
    with _PRICE_SNAPSHOT_CACHE_LOCK:
        current = _SYMBOL_FAILURES.get(_failure_key(symbol, provider))
        if not isinstance(current, dict):
            return True
        last_log = float(current.get("last_log") or 0.0)
        if now - last_log < _SYMBOL_FAILURE_COOLDOWN_SECONDS:
            return False
        current["last_log"] = now
        return True


def _load_price_cache_once(include_stale: bool = False):
    global _PRICE_CACHE_LOADED, _PRICE_CACHE_MTIME, _PRICE_CACHE_INCLUDE_STALE

    try:
        file_mtime = _PRICE_CACHE_FILE.stat().st_mtime if _PRICE_CACHE_FILE.exists() else 0.0
    except Exception:
        file_mtime = 0.0

    with _PRICE_SNAPSHOT_CACHE_LOCK:
        cache_has_required_freshness = not include_stale or _PRICE_CACHE_INCLUDE_STALE
        if _PRICE_CACHE_LOADED and file_mtime <= float(_PRICE_CACHE_MTIME or 0) and cache_has_required_freshness:
            return

        if file_mtime > float(_PRICE_CACHE_MTIME or 0) or (include_stale and not _PRICE_CACHE_INCLUDE_STALE):
            _PRICE_SNAPSHOT_CACHE.clear()
            _PRICE_CACHE_MTIME = file_mtime

        _PRICE_CACHE_LOADED = True
        if include_stale:
            _PRICE_CACHE_INCLUDE_STALE = True
        try:
            if not _PRICE_CACHE_FILE.exists():
                return
            raw = json.loads(_PRICE_CACHE_FILE.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return
            now = time.time()
            for key, value in raw.items():
                if not isinstance(value, dict):
                    continue
                timestamp = float(value.get("timestamp") or 0)
                payload = value.get("payload")
                if not _has_real_price_payload(payload):
                    continue
                if include_stale or now - timestamp <= _PRICE_CACHE_TTL_SECONDS:
                    _PRICE_SNAPSHOT_CACHE[str(key)] = {
                        "timestamp": timestamp,
                        "payload": payload,
                    }
        except Exception as exc:
            logger.warning("Failed to load market quote cache: %s", exc)


def _persist_price_cache():
    global _PRICE_CACHE_MTIME
    try:
        _PRICE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _PRICE_SNAPSHOT_CACHE_LOCK:
            payload = {
                key: value
                for key, value in _PRICE_SNAPSHOT_CACHE.items()
                if isinstance(value, dict)
                and isinstance(value.get("payload"), dict)
                and _has_real_price_payload(value["payload"])
            }
        tmp = _PRICE_CACHE_FILE.with_name(
            f"{_PRICE_CACHE_FILE.stem}.{os.getpid()}.{get_ident()}.tmp"
        )
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(tmp, _PRICE_CACHE_FILE)
        try:
            _PRICE_CACHE_MTIME = _PRICE_CACHE_FILE.stat().st_mtime
        except Exception:
            pass
    except Exception as exc:
        logger.warning("Failed to persist market quote cache: %s", exc)


def _chart_cache_key(symbol: str, interval: str) -> str:
    return f"{_cache_key(symbol)}:{str(interval or '1D').upper()}"


def get_cached_chart_data(symbol: str, interval: str = "1D"):
    start = time.perf_counter()
    with _PRICE_SNAPSHOT_CACHE_LOCK:
        cached = _CHART_DATA_CACHE.get(_chart_cache_key(symbol, interval))
    if not cached:
        record_cache_lookup("chart", time.perf_counter() - start, len(_CHART_DATA_CACHE))
        return None

    age = time.time() - float(cached.get("timestamp") or 0)
    if age > _CHART_CACHE_TTL_SECONDS:
        record_cache_lookup("chart", time.perf_counter() - start, len(_CHART_DATA_CACHE))
        return None

    rows = cached.get("rows")
    record_cache_lookup("chart", time.perf_counter() - start, len(_CHART_DATA_CACHE))
    return [dict(row) for row in rows] if isinstance(rows, list) else None


def _cache_chart_data(symbol: str, interval: str, rows: list):
    if not rows:
        return rows

    with _PRICE_SNAPSHOT_CACHE_LOCK:
        _CHART_DATA_CACHE[_chart_cache_key(symbol, interval)] = {
            "timestamp": time.time(),
            "rows": [dict(row) for row in rows],
        }
    return rows


def _cache_price_payload(symbol: str, payload: Optional[dict], persist: bool = True):
    if not _has_real_price_payload(payload):
        return payload

    payload = dict(payload or {})
    payload.setdefault("provider_symbol", _normalize_symbol(symbol))
    payload.setdefault("display_symbol", _normalize_ticker_display(symbol, _normalize_symbol(symbol)))
    key = _cache_key(symbol)
    with _PRICE_SNAPSHOT_CACHE_LOCK:
        _PRICE_SNAPSHOT_CACHE[key] = {
            "timestamp": time.time(),
            "payload": dict(payload),
        }
    if persist:
        _persist_price_cache()
    return payload


def _get_cached_price_payload(symbol: str, allow_stale: bool = False):
    _load_price_cache_once(include_stale=allow_stale)
    with _PRICE_SNAPSHOT_CACHE_LOCK:
        cached = _PRICE_SNAPSHOT_CACHE.get(_cache_key(symbol))
    if not cached:
        return None

    age = time.time() - float(cached.get("timestamp") or 0)
    if age > _PRICE_CACHE_TTL_SECONDS and not allow_stale:
        return None

    payload = dict(cached.get("payload") or {})
    if not _has_real_price_payload(payload):
        return None
    if not _payload_matches_requested_symbol(symbol, payload):
        return None
    if age > _PRICE_CACHE_TTL_SECONDS:
        payload["source"] = payload.get("source") or "stale_market_cache"
        payload["stale"] = True
    else:
        payload["source"] = payload.get("source") or "market_cache"
    payload["cache_age_seconds"] = round(age, 2)
    return payload


def batch_download(
    tickers: List[str],
    period: str = "1d",
    interval: str = "5m",
) -> Optional[pd.DataFrame]:
    normalized = []
    start = time.perf_counter()
    try:
        if not _network_provider_allowed():
            for ticker in tickers or []:
                _record_blocked_http_provider(ticker, "download")
            return None

        if not tickers or not isinstance(tickers, (list, tuple)):
            return None

        seen = set()
        for ticker in tickers:
            if not ticker or _is_permanently_blocked_symbol(ticker) or _is_symbol_cooling_down(ticker):
                continue
            normalized_symbol = _normalize_symbol(ticker)
            if not normalized_symbol or normalized_symbol in seen:
                continue
            seen.add(normalized_symbol)
            normalized.append(normalized_symbol)

        if not normalized:
            return None

        yf = _get_yfinance()
        data = yf.download(
            tickers=list(normalized),
            period=period,
            interval=interval,
            group_by="ticker",
            threads=False,
            auto_adjust=True,
            progress=False,
            prepost=True,
            timeout=8,
        )

        if data is None or data.empty:
            duration = time.perf_counter() - start
            for symbol in normalized:
                _mark_symbol_failure(symbol, error="empty_data")
                record_external_provider_call("yfinance", "download", duration_seconds=duration, success=False, symbol=symbol, error="empty_data")
            record_worker_stage_duration("market_download", duration, success=False)
            return None

        try:
            if hasattr(data.index, "tz") and data.index.tz is not None:
                data.index = data.index.tz_convert("UTC")
            else:
                data.index = data.index.tz_localize("UTC")
        except Exception:
            logger.warning("Timezone normalization failed")

        duration = time.perf_counter() - start
        for symbol in normalized:
            record_external_provider_call("yfinance", "download", duration_seconds=duration, success=True, symbol=symbol)
        record_worker_stage_duration("market_download", duration, success=True)
        return data
    except Exception as exc:
        duration = time.perf_counter() - start
        for symbol in normalized:
            _mark_symbol_failure(symbol, error=str(exc))
            record_external_provider_call("yfinance", "download", duration_seconds=duration, success=False, symbol=symbol, error=str(exc))
        record_worker_stage_duration("market_download", duration, success=False)
        if any(_should_log_symbol_failure(symbol) for symbol in normalized):
            logger.error("Batch download error: %s", exc)
        return None


def _extract_single_ticker_frame(data: Optional[pd.DataFrame], symbol: str) -> Optional[pd.DataFrame]:
    if data is None or data.empty:
        return None

    normalized_symbol = _normalize_symbol(symbol)
    columns = getattr(data, "columns", None)

    if columns is None:
        return None

    if hasattr(columns, "levels"):
        available = set(columns.get_level_values(0))

        if normalized_symbol not in available:
            return None

        frame = data[normalized_symbol].copy()
    else:
        frame = data.copy()

    return frame if frame is not None and not frame.empty else None


def get_ticker_frame(
    symbol: str,
    period: str = "1d",
    interval: str = "5m",
) -> Optional[pd.DataFrame]:
    if not _network_provider_allowed():
        _record_blocked_http_provider(symbol, "download")
        return None

    normalized_symbol = _normalize_symbol(symbol)
    data = batch_download([normalized_symbol], period=period, interval=interval)
    return _extract_single_ticker_frame(data, normalized_symbol)


def get_chart_data(symbol: str, interval: str = "1D"):
    normalized_interval = str(interval or "1D").upper()
    min_rows_map = {
        "1D": 12,
        "1W": 18,
        "1M": 18,
        "3M": 30,
        "6M": 40,
        "YTD": 40,
        "1Y": 60,
        "ALL": 60,
    }
    min_rows = min_rows_map.get(normalized_interval, 12)

    cached = get_cached_chart_data(symbol, interval)
    if cached and len(cached) >= min_rows:
        return cached

    if not _network_provider_allowed():
        _record_blocked_http_provider(symbol, "chart")
        return cached or []

    interval_map = {
        "1D": [("1d", "5m"), ("5d", "30m")],
        "1W": [("5d", "30m"), ("1mo", "1d")],
        "1M": [("1mo", "1d"), ("3mo", "1d")],
        "3M": [("3mo", "1d"), ("6mo", "1d")],
        "6M": [("6mo", "1d"), ("1y", "1d")],
        "YTD": [("ytd", "1d"), ("1y", "1d")],
        "1Y": [("1y", "1d"), ("2y", "1wk")],
        "ALL": [("5y", "1wk"), ("2y", "1d"), ("1y", "1d")],
    }

    frame = None
    for period, yf_interval in interval_map.get(normalized_interval, [("1d", "5m"), ("5d", "30m")]):
        frame = get_ticker_frame(symbol, period=period, interval=yf_interval)
        if frame is not None and not frame.empty:
            try:
                candidate_rows = frame.dropna(subset=["Close"]) if hasattr(frame, "dropna") else frame
            except Exception:
                candidate_rows = frame
            if candidate_rows is not None and len(candidate_rows) >= min_rows:
                frame = candidate_rows
                break
            frame = candidate_rows
        if frame is not None and not frame.empty and len(frame) >= min_rows:
            break

    if frame is None or frame.empty:
        return []

    try:
        frame = frame.dropna(subset=["Close"])
    except Exception:
        pass

    if frame is None or frame.empty:
        return []

    rows = []

    for index, row in frame.tail(240).iterrows():
        close = float(row.get("Close", 0) or 0)
        if close <= 0:
            continue

        rows.append(
            {
                "time": str(index),
                "open": float(row.get("Open", 0) or close),
                "high": float(row.get("High", 0) or close),
                "low": float(row.get("Low", 0) or close),
                "close": close,
                "volume": float(row.get("Volume", 0) or 0),
            }
        )

    return _cache_chart_data(symbol, interval, rows)


def _price_payload_from_frame(symbol: str, frame: Optional[pd.DataFrame]):
    if frame is None or frame.empty:
        return None

    try:
        frame = frame.dropna(subset=["Close"])
        if frame.empty:
            return None

        last = frame.iloc[-1]
        previous = frame.iloc[-2] if len(frame) > 1 else last
        last_close = float(last.get("Close", 0) or 0)
        previous_close = float(previous.get("Close", last_close) or last_close)
        if not math.isfinite(last_close) or not math.isfinite(previous_close):
            return None
        change = last_close - previous_close
        change_pct = 0.0 if previous_close == 0 else (change / previous_close) * 100
        last_volume = _positive_number_or_none(last.get("Volume"))
        volume_series = frame.get("Volume")
        average_volume = None
        if volume_series is not None:
            try:
                daily_volumes: dict[object, float] = {}
                for index, value in volume_series.items():
                    numeric_volume = _positive_number_or_none(value)
                    if numeric_volume is None:
                        continue
                    day_key = getattr(index, "date", lambda: index)()
                    daily_volumes[day_key] = daily_volumes.get(day_key, 0.0) + numeric_volume
                if daily_volumes:
                    latest_day = getattr(frame.index[-1], "date", lambda: frame.index[-1])()
                    last_volume = _positive_number_or_none(daily_volumes.get(latest_day)) or last_volume
                    average_source = [volume for day, volume in daily_volumes.items() if day != latest_day] or list(daily_volumes.values())
                    average_volume = sum(average_source) / len(average_source)
            except Exception:
                average_volume = None

        return {
            "symbol": _normalize_ticker_display(symbol, _normalize_symbol(symbol)),
            "provider_symbol": _normalize_symbol(symbol),
            "display_symbol": _normalize_ticker_display(symbol, _normalize_symbol(symbol)),
            "price": round(last_close, 4),
            "change": round(change, 4),
            "change_pct": round(change_pct, 4),
            "after_hours": None,
            "pre_market": None,
            "volume": last_volume,
            "average_volume": _positive_number_or_none(average_volume),
            "avg_volume": _positive_number_or_none(average_volume),
            "rel_volume": _relative_volume_or_none(last_volume, average_volume),
            "high": float(last.get("High", 0) or 0),
            "low": float(last.get("Low", 0) or 0),
        }
    except Exception as exc:
        logger.error("Price snapshot error for %s: %s", symbol, exc)
        return None


def _payload_with_volume_fallback(symbol: str, payload: Optional[dict]) -> Optional[dict]:
    if not payload or _positive_number_or_none(payload.get("volume")) is not None:
        return payload
    fast_payload = _price_payload_from_fast_info(symbol)
    fast_volume = _positive_number_or_none((fast_payload or {}).get("volume"))
    if fast_volume is None:
        return payload
    enriched = dict(payload)
    enriched["volume"] = fast_volume
    for field in ("average_volume", "avg_volume", "rel_volume"):
        if not _positive_number_or_none(enriched.get(field)) and fast_payload:
            enriched[field] = fast_payload.get(field)
    if not _positive_number_or_none(enriched.get("high")) and fast_payload:
        enriched["high"] = fast_payload.get("high")
    if not _positive_number_or_none(enriched.get("low")) and fast_payload:
        enriched["low"] = fast_payload.get("low")
    enriched["source"] = enriched.get("source") or "market_cache"
    enriched["volume_source"] = "fast_info"
    return enriched


def _fast_info_get(data, *keys):
    for key in keys:
        try:
            if isinstance(data, dict):
                value = data.get(key)
            else:
                value = getattr(data, key, None)
        except Exception:
            value = None
        if value is not None:
            return value
    return None


def _positive_number_or_none(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or numeric <= 0:
        return None
    return numeric


def _relative_volume_or_none(volume, average_volume):
    current = _positive_number_or_none(volume)
    average = _positive_number_or_none(average_volume)
    if current is None or average is None:
        return None
    return round(max(0.01, min(current / average, 25.0)), 4)


def _price_payload_from_fast_info(symbol: str):
    """Fallback for symbols where intraday history is temporarily unavailable."""
    start = time.perf_counter()
    try:
        if not _network_provider_allowed():
            _record_blocked_http_provider(symbol, "fast_info")
            return None

        normalized_symbol = _normalize_symbol(symbol)
        yf = _get_yfinance()
        ticker = yf.Ticker(normalized_symbol)
        fast_info = getattr(ticker, "fast_info", None) or {}
        last_price = _fast_info_get(
            fast_info,
            "last_price",
            "lastPrice",
            "regular_market_price",
            "regularMarketPrice",
        )
        previous_close = _fast_info_get(
            fast_info,
            "previous_close",
            "previousClose",
            "regular_market_previous_close",
            "regularMarketPreviousClose",
        )
        info = {}
        if last_price is None:
            info = getattr(ticker, "info", None) or {}
            last_price = _fast_info_get(info, "regularMarketPrice", "currentPrice", "previousClose")
            previous_close = previous_close or _fast_info_get(info, "regularMarketPreviousClose", "previousClose")

        if last_price is None:
            duration = time.perf_counter() - start
            _mark_symbol_failure(normalized_symbol, error="empty_price")
            record_external_provider_call("yfinance", "fast_info", duration_seconds=duration, success=False, symbol=normalized_symbol, error="empty_price")
            return None

        last_price = float(last_price)
        previous_close = float(previous_close or last_price)
        if last_price <= 0:
            duration = time.perf_counter() - start
            _mark_symbol_failure(normalized_symbol, error="invalid_price")
            record_external_provider_call("yfinance", "fast_info", duration_seconds=duration, success=False, symbol=normalized_symbol, error="invalid_price")
            return None

        change = last_price - previous_close
        change_pct = 0.0 if previous_close == 0 else (change / previous_close) * 100
        volume = _fast_info_get(fast_info, "last_volume", "lastVolume", "regular_market_volume", "regularMarketVolume")
        if volume is None:
            info = info or getattr(ticker, "info", None) or {}
            volume = _fast_info_get(info, "regularMarketVolume", "volume")
        average_volume = _fast_info_get(
            fast_info,
            "ten_day_average_volume",
            "tenDayAverageVolume",
            "three_month_average_volume",
            "threeMonthAverageVolume",
        )
        if average_volume is None:
            info = info or getattr(ticker, "info", None) or {}
            average_volume = _fast_info_get(
                info,
                "averageVolume",
                "averageVolume10days",
                "averageDailyVolume10Day",
                "averageVolume3months",
            )
        high = _fast_info_get(fast_info, "day_high", "dayHigh", "regular_market_day_high", "regularMarketDayHigh")
        low = _fast_info_get(fast_info, "day_low", "dayLow", "regular_market_day_low", "regularMarketDayLow")
        positive_volume = _positive_number_or_none(volume)
        positive_average_volume = _positive_number_or_none(average_volume)

        payload = {
            "symbol": _normalize_ticker_display(symbol, normalized_symbol),
            "provider_symbol": normalized_symbol,
            "display_symbol": _normalize_ticker_display(symbol, normalized_symbol),
            "price": round(last_price, 4),
            "change": round(change, 4),
            "change_pct": round(change_pct, 4),
            "after_hours": None,
            "pre_market": None,
            "volume": positive_volume,
            "average_volume": positive_average_volume,
            "avg_volume": positive_average_volume,
            "rel_volume": _relative_volume_or_none(positive_volume, positive_average_volume),
            "high": float(high or last_price),
            "low": float(low or last_price),
        }
        duration = time.perf_counter() - start
        record_external_provider_call("yfinance", "fast_info", duration_seconds=duration, success=True, symbol=normalized_symbol)
        return payload
    except Exception as exc:
        duration = time.perf_counter() - start
        _mark_symbol_failure(symbol, error=str(exc))
        record_external_provider_call("yfinance", "fast_info", duration_seconds=duration, success=False, symbol=symbol, error=str(exc))
        if _should_log_symbol_failure(symbol):
            logger.warning("Fast quote fallback failed for %s: %s", symbol, exc)
        return None


def get_price_snapshot(symbol: str):
    if not _network_provider_allowed():
        _record_blocked_http_provider(symbol, "quote")
        return _get_cached_price_payload(symbol, allow_stale=True)

    if _is_permanently_blocked_symbol(symbol):
        return _get_cached_price_payload(symbol)

    if _is_symbol_cooling_down(symbol):
        return _get_cached_price_payload(symbol, allow_stale=True)

    if _prefer_b3_reference_proxy(symbol):
        reference_payload = _reference_payload_for_b3_future(symbol)
        if reference_payload:
            _clear_symbol_failure(symbol)
            return _cache_price_payload(symbol, reference_payload)

    for period, interval in (("5d", "30m"), ("1d", "5m"), ("1mo", "1d")):
        frame = get_ticker_frame(symbol, period=period, interval=interval)
        payload = _price_payload_from_frame(symbol, frame)
        if payload:
            payload = _payload_with_volume_fallback(symbol, payload)
            _clear_symbol_failure(symbol)
            return _cache_price_payload(symbol, payload)
    payload = _price_payload_from_fast_info(symbol)
    if payload:
        _clear_symbol_failure(symbol)
        return _cache_price_payload(symbol, payload)

    reference_payload = _reference_payload_for_b3_future(symbol)
    if reference_payload:
        _clear_symbol_failure(symbol)
        return _cache_price_payload(symbol, reference_payload)

    proxy_symbol = None if _is_bdr_symbol(symbol) else _proxy_symbol_for(symbol)
    if proxy_symbol and proxy_symbol != _normalize_symbol(symbol):
        proxy_payload = _get_cached_price_payload(proxy_symbol) or get_price_snapshot(proxy_symbol)
        if _has_real_price_payload(proxy_payload):
            resolved = dict(proxy_payload)
            resolved["symbol"] = _normalize_ticker_display(symbol, _normalize_symbol(symbol))
            resolved["source"] = "proxy_market"
            return _cache_price_payload(symbol, resolved)

    _mark_symbol_failure(symbol)
    return _get_cached_price_payload(symbol)


def get_price_snapshots(symbols: List[str]):
    _load_price_cache_once()
    if not symbols:
        return {}

    if not _network_provider_allowed():
        for symbol in symbols:
            _record_blocked_http_provider(symbol, "quote_batch")
        return get_cached_price_snapshots(symbols, allow_stale=True)

    unique_symbols = []
    seen = set()
    for symbol in symbols:
        if _is_permanently_blocked_symbol(symbol):
            continue
        display_symbol = _normalize_ticker_display(symbol, _normalize_symbol(symbol))
        if not display_symbol or display_symbol in seen:
            continue
        seen.add(display_symbol)
        unique_symbols.append(display_symbol)

    payloads = {}
    cache_changed = False

    cached_payloads = get_cached_price_snapshots(unique_symbols)
    missing_symbols = []
    for symbol in unique_symbols:
        cached = cached_payloads.get(symbol)
        if cached and _positive_number_or_none(cached.get("volume")) is not None:
            payloads[symbol] = cached
        else:
            missing_symbols.append(symbol)

    if not missing_symbols:
        return payloads

    direct_symbols = []
    proxy_symbol_by_display = {}
    proxy_download_symbols = []
    seen_proxy_symbols = set()
    for symbol in missing_symbols:
        normalized_symbol = _normalize_symbol(symbol)
        if _is_symbol_cooling_down(symbol):
            stale = _get_cached_price_payload(symbol, allow_stale=True)
            if stale:
                payloads[symbol] = stale
            continue
        if _prefer_b3_reference_proxy(symbol):
            reference_payload = _reference_payload_for_b3_future(symbol)
            if reference_payload:
                payloads[symbol] = _cache_price_payload(symbol, reference_payload, persist=False)
                _clear_symbol_failure(symbol)
                cache_changed = True
                continue
        proxy_symbol = None if _is_bdr_symbol(symbol) else _proxy_symbol_for(symbol)
        if proxy_symbol and proxy_symbol != normalized_symbol:
            proxy_symbol_by_display[symbol] = proxy_symbol
            if proxy_symbol not in seen_proxy_symbols:
                seen_proxy_symbols.add(proxy_symbol)
                proxy_download_symbols.append(proxy_symbol)
            continue
        direct_symbols.append(symbol)

    data = batch_download(direct_symbols + proxy_download_symbols, period="5d", interval="30m")
    for symbol in missing_symbols:
        payload = None
        proxy_symbol = proxy_symbol_by_display.get(symbol)

        if data is not None and not data.empty:
            frame_symbol = proxy_symbol or symbol
            frame = _extract_single_ticker_frame(data, frame_symbol)
            payload = _price_payload_from_frame(frame_symbol, frame)
            if payload:
                payload = _payload_with_volume_fallback(frame_symbol, payload)

        if proxy_symbol:
            if not payload:
                payload = _get_cached_price_payload(proxy_symbol) or get_price_snapshot(proxy_symbol)
            if _has_real_price_payload(payload):
                resolved = dict(payload)
                resolved["symbol"] = _normalize_ticker_display(symbol, _normalize_symbol(symbol))
                resolved["source"] = "proxy_market"
                payloads[symbol] = _cache_price_payload(symbol, resolved, persist=False)
                _clear_symbol_failure(symbol)
                cache_changed = True
                continue
        elif not payload:
            payload = get_price_snapshot(symbol)

        if _has_real_price_payload(payload):
            payloads[symbol] = _cache_price_payload(symbol, payload, persist=False)
            _clear_symbol_failure(symbol)
            cache_changed = True
            continue

        cached = _get_cached_price_payload(symbol)
        if cached:
            payloads[symbol] = cached
        else:
            _mark_symbol_failure(symbol)

    if cache_changed:
        _persist_price_cache()

    return payloads


def get_cached_price_snapshots(symbols: List[str], allow_stale: bool = False):
    start = time.perf_counter()
    _load_price_cache_once(include_stale=allow_stale)
    payloads = {}
    with _PRICE_SNAPSHOT_CACHE_LOCK:
        now = time.time()
        for symbol in symbols or []:
            key = _cache_key(symbol)
            if not key:
                continue
            cached = _PRICE_SNAPSHOT_CACHE.get(key)
            if not cached:
                continue
            age = now - float(cached.get("timestamp") or 0)
            if age > _PRICE_CACHE_TTL_SECONDS and not allow_stale:
                continue
            payload = dict(cached.get("payload") or {})
            if not _has_real_price_payload(payload):
                continue
            if not _payload_matches_requested_symbol(symbol, payload):
                continue
            if age > _PRICE_CACHE_TTL_SECONDS:
                payload["source"] = payload.get("source") or "stale_market_cache"
                payload["stale"] = True
            else:
                payload["source"] = payload.get("source") or "market_cache"
            payload["cache_age_seconds"] = round(age, 2)
            payloads[key] = payload
    record_cache_lookup("quote", time.perf_counter() - start, len(_PRICE_SNAPSHOT_CACHE))
    return payloads
