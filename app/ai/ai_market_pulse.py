# =====================================================
# STOCKNEWSBR AI MARKET PULSE
# Ultra Fast + Crash Safe
# =====================================================

import logging
from datetime import datetime, timezone

from app.cache.signal_cache import signal_cache

logger = logging.getLogger("stocknewsbr.market_pulse")


def market_pulse(signals=None):

    timestamp = datetime.now(timezone.utc).isoformat()

    try:

        results = signals if signals is not None else signal_cache.get()

        if not results or not isinstance(results, list):

            return {
                "sentiment": "neutral",
                "bullish_signals": 0,
                "bearish_signals": 0,
                "total_signals": 0,
                "timestamp": timestamp
            }

        bullish = 0
        bearish = 0
        valid_signals = 0

        for r in results:

            if not isinstance(r, dict):
                continue

            score = r.get("score")

            if not isinstance(score, (int, float)):
                continue

            valid_signals += 1

            if score >= 60:
                bullish += 1

            elif score <= 40:
                bearish += 1

        if valid_signals == 0:

            return {
                "sentiment": "neutral",
                "bullish_signals": 0,
                "bearish_signals": 0,
                "total_signals": 0,
                "timestamp": timestamp
            }

        bullish_ratio = bullish / valid_signals
        bearish_ratio = bearish / valid_signals

        if bullish_ratio > 0.55:
            sentiment = "bullish"

        elif bearish_ratio > 0.55:
            sentiment = "bearish"

        else:
            sentiment = "neutral"

        return {

            "sentiment": sentiment,
            "bullish_signals": bullish,
            "bearish_signals": bearish,
            "total_signals": valid_signals,
            "bullish_ratio": round(bullish_ratio, 3),
            "bearish_ratio": round(bearish_ratio, 3),
            "timestamp": timestamp

        }

    except Exception as e:

        logger.exception("Market pulse error")

        return {

            "sentiment": "unknown",
            "bullish_signals": 0,
            "bearish_signals": 0,
            "total_signals": 0,
            "timestamp": timestamp,
            "error": str(e)
        }
