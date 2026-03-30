# =====================================================
# PRICE EVENT ENGINE (V36 HARDENED)
# =====================================================

import logging
import time
from typing import Dict, List, Any

logger = logging.getLogger("stocknewsbr.engine.events")

# last known prices
_last_prices: Dict[str, float] = {}

# last event timestamp (anti storm)
_last_event_ts: Dict[str, float] = {}

PRICE_EPSILON = 0.0005
EVENT_COOLDOWN = 0.5  # seconds


# =====================================================
# SAFE FLOAT
# =====================================================

def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


# =====================================================
# DETECT PRICE EVENTS
# =====================================================

def detect_price_events(pool: Dict) -> List[Dict]:
    """
    Event driven detection for price movements.

    Optimized for:
    - minimal CPU usage
    - event storm protection
    - crash safety
    """

    if not pool:
        return []

    events = []
    now = time.time()

    try:

        for ticker, df in pool.items():

            try:

                if df is None or "Close" not in df:
                    continue

                price = _safe_float(df["Close"].iloc[-1])

                if price <= 0:
                    continue

                last = _last_prices.get(ticker)

                # first observation
                if last is None:

                    _last_prices[ticker] = price
                    _last_event_ts[ticker] = now
                    continue

                change = abs(price - last) / (last + 1e-12)

                if change < PRICE_EPSILON:
                    continue

                # anti event storm
                last_ts = _last_event_ts.get(ticker, 0)

                if now - last_ts < EVENT_COOLDOWN:
                    continue

                events.append({
                    "ticker": ticker,
                    "price": price,
                    "change": change
                })

                _last_prices[ticker] = price
                _last_event_ts[ticker] = now

            except Exception:
                continue

        return events

    except Exception as e:

        logger.exception("Price event engine failure: %s", e)

        return []