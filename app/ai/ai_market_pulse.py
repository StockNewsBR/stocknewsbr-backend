# =====================================================
# STOCKNEWSBR AI MARKET PULSE
# Ultra Fast + Crash Safe
# =====================================================

import logging
from datetime import datetime, timezone

from app.cache.signal_cache import signal_cache

logger = logging.getLogger("stocknewsbr.market_pulse")

_ACTIONABLE_SIGNALS = {"BUY", "SELL", "SHORT", "COVER"}
_BULLISH_ACTIONS = {"BUY", "COVER"}
_BEARISH_ACTIONS = {"SELL", "SHORT"}
_BLOCKED_DATA_QUALITIES = {
    "score_only",
    "score only",
    "missing",
    "empty",
    "stale",
    "no_price",
    "no-price",
    "no price",
    "provider_failed",
    "provider-failed",
    "provider failed",
    "failed",
    "error",
    "timeout",
    "unavailable",
    "invalid",
}
_BLOCKED_STATUSES = _BLOCKED_DATA_QUALITIES


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _has_positive_value(row, *keys):
    return any(_safe_float(row.get(key)) > 0 for key in keys)


def _signal_value(row):
    return str(row.get("trade_action") or row.get("signal") or row.get("action") or "").upper().strip()


def _has_blocking_reasons(row):
    reasons = row.get("blocked_reasons") or row.get("warnings") or []
    if isinstance(reasons, str):
        return bool(reasons.strip())
    if isinstance(reasons, (list, tuple, set)):
        return any(str(item).strip() for item in reasons)
    return False


def _is_actionable_row(row):
    if not isinstance(row, dict):
        return False
    signal = _signal_value(row)
    if signal not in _ACTIONABLE_SIGNALS:
        return False
    if row.get("decision_ready") is False:
        return False
    if row.get("stale") is True or row.get("is_stale") is True:
        return False
    if str(row.get("data_quality") or "").lower().strip() in _BLOCKED_DATA_QUALITIES:
        return False
    for status_key in ("quote_status", "status", "provider_status", "market_data_status"):
        if str(row.get(status_key) or "").lower().strip() in _BLOCKED_STATUSES:
            return False
    if row.get("provider_failed") is True or row.get("provider_error") is True:
        return False
    if _has_blocking_reasons(row):
        return False
    if not _has_positive_value(row, "price", "close", "last_price"):
        return False
    if not _has_positive_value(row, "volume", "last_volume"):
        return False
    return True


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

            if not _is_actionable_row(r):
                continue

            valid_signals += 1

            action = _signal_value(r)

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
