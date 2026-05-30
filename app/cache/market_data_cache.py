import logging
import threading
import time
from typing import Iterable, Optional, Tuple

from app.config import SYMBOLS
from app.system.system_metrics import current_provider_call_source, record_external_provider_call, record_worker_stage_duration

logger = logging.getLogger("stocknewsbr.market_cache")
_YFINANCE = None

CACHE_TTL = 60
PROVIDER_FAILURE_COOLDOWN_SECONDS = 180

_cache_data = None
_cache_key: Tuple[str, ...] = tuple()
_last_update = 0.0
_provider_cooldown_until = 0.0
_last_provider_failure_log = 0.0
_lock = threading.RLock()


def _get_yfinance():
    global _YFINANCE
    if _YFINANCE is None:
        import yfinance as yf_module

        _YFINANCE = yf_module
    return _YFINANCE


def _normalize_tickers(tickers: Optional[Iterable[str]]) -> Tuple[str, ...]:
    if tickers is None:
        tickers = SYMBOLS

    normalized = []
    seen = set()

    for ticker in tickers:
        if not ticker or ticker in seen:
            continue

        seen.add(ticker)
        normalized.append(str(ticker).upper())

    return tuple(normalized)


def _extract_subset(data, tickers: Tuple[str, ...]):
    if data is None:
        return None

    columns = getattr(data, "columns", None)

    if columns is None:
        return None

    if hasattr(columns, "levels"):
        available = set(columns.get_level_values(0))
        selected = [ticker for ticker in tickers if ticker in available]

        if not selected:
            return None

        if len(selected) == 1:
            return data[selected[0]]

        return data.loc[:, data.columns.get_level_values(0).isin(selected)]

    if len(tickers) == 1:
        return data

    return None


def _cache_satisfies(requested_key: Tuple[str, ...], now: float) -> bool:
    if _cache_data is None:
        return False

    if now - _last_update >= CACHE_TTL:
        return False

    return set(requested_key).issubset(set(_cache_key))


def _provider_in_cooldown(now: float) -> bool:
    return now < _provider_cooldown_until


def _mark_provider_cooldown(reason: str):
    global _provider_cooldown_until
    global _last_provider_failure_log

    now = time.time()
    _provider_cooldown_until = max(_provider_cooldown_until, now + PROVIDER_FAILURE_COOLDOWN_SECONDS)
    if now - _last_provider_failure_log >= PROVIDER_FAILURE_COOLDOWN_SECONDS:
        logger.warning(
            "Market provider cooldown active for %ss after %s",
            PROVIDER_FAILURE_COOLDOWN_SECONDS,
            reason,
        )
        _last_provider_failure_log = now


def fetch_market_data(tickers: Tuple[str, ...]):
    start = time.perf_counter()
    now = time.time()
    if current_provider_call_source() == "http":
        for ticker in tickers:
            record_external_provider_call(
                "yfinance",
                "market_cache_download_blocked_http",
                duration_seconds=0.0,
                success=False,
                symbol=ticker,
                error="http_provider_blocked",
            )
        return None

    if _provider_in_cooldown(now):
        record_worker_stage_duration("market_download_cooldown", 0.0, success=False)
        return None

    try:
        yf = _get_yfinance()
        data = yf.download(
            tickers=list(tickers),
            period="1d",
            interval="5m",
            group_by="ticker",
            threads=False,
            progress=False,
            auto_adjust=True,
            prepost=True,
            timeout=8,
        )

        if data is None or len(data) == 0:
            duration = time.perf_counter() - start
            for ticker in tickers:
                record_external_provider_call("yfinance", "market_cache_download", duration_seconds=duration, success=False, symbol=ticker, error="empty_data")
            record_worker_stage_duration("market_download", duration, success=False)
            _mark_provider_cooldown("empty_data")
            return None

        duration = time.perf_counter() - start
        for ticker in tickers:
            record_external_provider_call("yfinance", "market_cache_download", duration_seconds=duration, success=True, symbol=ticker)
        record_worker_stage_duration("market_download", duration, success=True)
        return data

    except Exception as exc:
        duration = time.perf_counter() - start
        for ticker in tickers:
            record_external_provider_call("yfinance", "market_cache_download", duration_seconds=duration, success=False, symbol=ticker, error=str(exc))
        record_worker_stage_duration("market_download", duration, success=False)
        _mark_provider_cooldown(str(exc) or "exception")
        return None


def get_market_data(tickers=None):
    global _cache_data
    global _cache_key
    global _last_update

    requested_key = _normalize_tickers(tickers)

    if not requested_key:
        return None

    now = time.time()

    with _lock:
        if _cache_satisfies(requested_key, now):
            return _extract_subset(_cache_data, requested_key)

    data = fetch_market_data(requested_key)

    if data is None:
        with _lock:
            if _cache_satisfies(requested_key, now):
                return _extract_subset(_cache_data, requested_key)

        return None

    with _lock:
        _cache_data = data
        _cache_key = requested_key
        _last_update = now
        return _extract_subset(_cache_data, requested_key)


class MarketDataCacheCompatibility:
    def get(self, ticker: Optional[str] = None, tickers: Optional[Iterable[str]] = None):
        if tickers is not None:
            return get_market_data(tickers)

        if ticker:
            return get_market_data([ticker])

        return get_market_data()

    def clear(self):
        global _cache_data
        global _cache_key
        global _last_update

        with _lock:
            _cache_data = None
            _cache_key = tuple()
            _last_update = 0.0


market_data_cache = MarketDataCacheCompatibility()


def get_cache(ticker: Optional[str] = None):
    if ticker:
        return market_data_cache.get(ticker=ticker)

    return get_market_data()
