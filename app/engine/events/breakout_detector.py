# =====================================================
# BREAKOUT DETECTOR
# =====================================================
# High performance breakout detection
# Used by event detection engine
# =====================================================

import numpy as np
import logging

logger = logging.getLogger("stocknewsbr.breakout")


def detect_breakout(df, lookback=20):

    try:

        close = df["Close"].values

        if close.size < lookback + 1:
            return False

        resistance = np.max(close[-lookback-1:-1])

        last_price = close[-1]

        return bool(last_price > resistance)

    except Exception as e:

        logger.debug(f"Breakout detection error: {e}")

        return False


# =====================================================
# BATCH DETECTION
# =====================================================

def detect_breakouts(pool, lookback=20):

    results = {}

    try:

        for ticker, df in pool.items():

            if df is None or len(df) < lookback + 1:
                continue

            if detect_breakout(df, lookback):

                results[ticker] = "breakout"

    except Exception as e:

        logger.error(f"Breakout batch failure: {e}")

    return results