# =====================================================
# STOCKNEWSBR AI MARKET PULSE
# Ultra Fast + Crash Safe
# =====================================================

import logging
from datetime import datetime, timezone

from app.cache.snapshot_cache import get_snapshot_signals
from app.services.snapshot_contract import is_actionable_snapshot_row, snapshot_signal_value

logger = logging.getLogger("stocknewsbr.market_pulse")

_BULLISH_ACTIONS = {"BUY", "COVER"}
_BEARISH_ACTIONS = {"SELL", "SHORT"}


def market_pulse(signals=None):

    timestamp = datetime.now(timezone.utc).isoformat()

    try:

        results = signals if signals is not None else get_snapshot_signals()

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

            if not is_actionable_snapshot_row(r):
                continue

            valid_signals += 1

            action = snapshot_signal_value(r)

            if action in _BULLISH_ACTIONS:
                bullish += 1

            elif action in _BEARISH_ACTIONS:
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
