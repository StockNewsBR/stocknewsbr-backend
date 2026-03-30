import logging
import threading
import time
from typing import Iterable, Optional, Tuple

import yfinance as yf

from app.config import SYMBOLS

logger = logging.getLogger("stocknewsbr.market_cache")

CACHE_TTL = 60

_cache_data = None
_cache_key: Tuple[str, ...] = tuple()
_last_update = 0.0
_lock = threading.RLock()


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


def fetch_market_data(tickers: Tuple[str, ...]):
    try:
        data = yf.download(
            tickers=list(tickers),
            period="1d",
            interval="5m",
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=True,
            prepost=True,
        )

        if data is None or len(data) == 0:
            logger.warning("Market download returned empty")
            return None

        return data

    except Exception as exc:
        logger.error("Market download error: %s", exc)
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
