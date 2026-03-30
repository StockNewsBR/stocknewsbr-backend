import logging
import os
import threading
import time
from typing import Dict

from app.cache.market_data_cache import get_market_data
from app.market.market_store import market_store
from app.market.market_universe import get_all_tickers

logger = logging.getLogger("stocknewsbr.market.pool")

WARM_POOL_TTL = max(5, int(os.getenv("WARM_POOL_TTL", "30")))

_pool: Dict[str, object] = {}
_last_update = 0.0
_lock = threading.RLock()


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


def update_pool(force_refresh: bool = False):
    global _pool
    global _last_update

    tickers = get_all_tickers()

    if not tickers:
        return {}

    now = time.time()

    with _lock:
        if _pool and not force_refresh and now - _last_update < WARM_POOL_TTL:
            return dict(_pool)

    data = get_market_data(tickers)
    new_pool = _build_pool(data, tickers)

    if not new_pool:
        logger.warning("Warm data pool refresh returned empty dataset")

        with _lock:
            return dict(_pool)

    with _lock:
        _pool = dict(new_pool)
        _last_update = now
        market_store.update(_pool)
        return dict(_pool)


def get_market_pool(force_refresh: bool = False):
    now = time.time()

    with _lock:
        if _pool and not force_refresh and now - _last_update < WARM_POOL_TTL:
            return dict(_pool)

    cached_store = market_store.get()

    if cached_store and not force_refresh:
        with _lock:
            _pool.update(cached_store)
            return dict(_pool)

    return update_pool(force_refresh=force_refresh)
