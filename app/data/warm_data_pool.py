import logging
import os
import threading
import time
from typing import Dict

import pandas as pd

from app.cache.market_data_cache import get_market_data
from app.market.market_data_loader import get_cached_chart_data
from app.market.market_store import market_store
from app.market.market_universe import get_all_tickers

logger = logging.getLogger("stocknewsbr.market.pool")

WARM_POOL_TTL = max(5, int(os.getenv("WARM_POOL_TTL", "30")))

_pool: Dict[str, object] = {}
_last_update = 0.0
_last_empty_log = 0.0
_lock = threading.RLock()
_refresh_lock = threading.Lock()


def _build_pool(data, tickers):
    if data is None:
        return {}

    columns = getattr(data, "columns", None)

    if columns is None:
        return {}

    pool = {}

    if hasattr(columns, "levels"):
        available = set(columns.get_level_values(0))

        for ticker in tickers:
            if ticker not in available:
                continue

            try:
                frame = data[ticker].dropna(how="all")
            except Exception:
                continue

            if len(frame) >= 50:
                pool[ticker] = frame

        return pool

    if len(tickers) == 1 and len(data) >= 50:
        pool[tickers[0]] = data.dropna(how="all")

    return pool


def _build_persistent_chart_pool(tickers, existing_pool=None):
    pool = {}
    existing = set(existing_pool or {})

    for ticker in tickers:
        if ticker in existing:
            continue

        rows = get_cached_chart_data(ticker, "1D")
        if not rows:
            continue

        try:
            frame = pd.DataFrame(rows).rename(
                columns={
                    "open": "Open",
                    "high": "High",
                    "low": "Low",
                    "close": "Close",
                    "volume": "Volume",
                }
            )
            frame.index = pd.to_datetime(frame.pop("time"), utc=True, errors="coerce")
            frame = frame.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
            latest = frame.iloc[-1]
            if len(frame) < 50 or float(latest["Close"]) <= 0 or float(latest["Volume"]) <= 0:
                continue
        except (KeyError, TypeError, ValueError, IndexError):
            continue

        frame.attrs["market_data_source"] = "persistent_chart_cache"
        pool[ticker] = frame

    return pool


def update_pool(force_refresh: bool = False):
    global _pool
    global _last_update
    global _last_empty_log

    with _refresh_lock:
        return _update_pool_locked(force_refresh)


def _update_pool_locked(force_refresh: bool = False):
    global _pool
    global _last_update
    global _last_empty_log

    now = time.time()

    with _lock:
        if _pool and not force_refresh and now - _last_update < WARM_POOL_TTL:
            return dict(_pool)

    tickers = get_all_tickers()

    if not tickers:
        return {}

    data = get_market_data(tickers)
    now = time.time()
    new_pool = _build_pool(data, tickers)
    cached_pool = _build_persistent_chart_pool(tickers, new_pool)
    if cached_pool:
        logger.info("Warm data pool using fresh persistent chart cache for %d symbols", len(cached_pool))
        new_pool.update(cached_pool)

    if not new_pool:
        if now - _last_empty_log >= WARM_POOL_TTL:
            logger.warning("Warm data pool refresh returned empty dataset | reason=provider_and_fresh_cache_unavailable")
            _last_empty_log = now

        with _lock:
            return dict(_pool)

    with _lock:
        _pool = dict(new_pool)
        _last_update = now
        try:
            market_store.update(_pool)
        except Exception as exc:
            # Mission 31F: persistence failure must not drop the freshly
            # built in-memory snapshot. The error is logged, not masked.
            logger.warning("Warm data pool persistence failed: %s", exc)
        return dict(_pool)


def get_market_pool(force_refresh: bool = False):
    global _last_update

    now = time.time()

    with _lock:
        if _pool and not force_refresh and now - _last_update < WARM_POOL_TTL:
            return dict(_pool)

    if not force_refresh:
        with _refresh_lock:
            now = time.time()
            with _lock:
                if _pool and now - _last_update < WARM_POOL_TTL:
                    return dict(_pool)

            cached_store = market_store.get()
            if cached_store:
                with _lock:
                    _pool.update(cached_store)
                    _last_update = now
                    return dict(_pool)

    return update_pool(force_refresh=force_refresh)
