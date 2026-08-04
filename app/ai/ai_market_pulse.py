# =====================================================
# STOCKNEWSBR AI MARKET PULSE
# Ultra Fast + Crash Safe
# =====================================================

import logging
from datetime import datetime, timezone

from app.cache.snapshot_cache import get_snapshot_signals
from app.services.snapshot_contract import (
    is_actionable_snapshot_row,
    is_blocked_snapshot_row,
    is_watchlist_snapshot_row,
    snapshot_row_orientation,
    snapshot_row_summary,
    summarize_snapshot_rows,
)

logger = logging.getLogger("stocknewsbr.market_pulse")

_GROUP_SAMPLE_LIMIT = 25


def _empty_pulse(timestamp, sentiment="neutral", error=None):
    payload = {
        "sentiment": sentiment,
        "bullish_signals": 0,
        "bearish_signals": 0,
        "total_signals": 0,
        "scanned_signals": 0,
        "bullish_candidates": 0,
        "actionable_bullish": 0,
        "bearish_candidates": 0,
        "actionable_bearish": 0,
        "blocked_signals": 0,
        "watchlist_candidates": 0,
        "bullish_ratio": 0.0,
        "bearish_ratio": 0.0,
        "timestamp": timestamp,
        "signal_groups": {
            "bullish_candidates": [],
            "actionable_bullish": [],
            "bearish_candidates": [],
            "actionable_bearish": [],
            "blocked_signals": [],
            "watchlist_candidates": [],
        },
    }
    if error:
        payload["error"] = error
    return payload


def market_pulse(signals=None):

    timestamp = datetime.now(timezone.utc).isoformat()

    try:

        results = signals if signals is not None else get_snapshot_signals()

        if not results or not isinstance(results, list):
            return _empty_pulse(timestamp)

        rows = [r for r in results if isinstance(r, dict)]
        stats = summarize_snapshot_rows(rows)
        groups = {
            "bullish_candidates": [],
            "actionable_bullish": [],
            "bearish_candidates": [],
            "actionable_bearish": [],
            "blocked_signals": [],
            "watchlist_candidates": [],
        }

        for row in rows:
            orientation = snapshot_row_orientation(row)
            actionable = is_actionable_snapshot_row(row)

            if orientation == "bullish":
                groups["bullish_candidates"].append(snapshot_row_summary(row))
                if actionable:
                    groups["actionable_bullish"].append(snapshot_row_summary(row))

            elif orientation == "bearish":
                groups["bearish_candidates"].append(snapshot_row_summary(row))
                if actionable:
                    groups["actionable_bearish"].append(snapshot_row_summary(row))

            if is_blocked_snapshot_row(row):
                groups["blocked_signals"].append(snapshot_row_summary(row))

            if is_watchlist_snapshot_row(row):
                groups["watchlist_candidates"].append(snapshot_row_summary(row))

        groups = {
            key: value[:_GROUP_SAMPLE_LIMIT]
            for key, value in groups.items()
        }

        bullish = stats["actionable_bullish"]
        bearish = stats["actionable_bearish"]
        valid_signals = stats["actionable"]

        if valid_signals == 0:
            payload = _empty_pulse(timestamp)
            payload.update(
                {
                    "scanned_signals": stats["total_signals"],
                    "bullish_candidates": stats["bullish_candidates"],
                    "bearish_candidates": stats["bearish_candidates"],
                    "blocked_signals": stats["blocked_signals"],
                    "watchlist_candidates": stats["watchlist_candidates"],
                    "signal_groups": groups,
                }
            )
            return payload

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
            "scanned_signals": stats["total_signals"],
            "bullish_candidates": stats["bullish_candidates"],
            "actionable_bullish": bullish,
            "bearish_candidates": stats["bearish_candidates"],
            "actionable_bearish": bearish,
            "blocked_signals": stats["blocked_signals"],
            "watchlist_candidates": stats["watchlist_candidates"],
            "bullish_ratio": round(bullish_ratio, 3),
            "bearish_ratio": round(bearish_ratio, 3),
            "timestamp": timestamp,
            "signal_groups": groups

        }

    except Exception as e:

        logger.exception("Market pulse error")

        return _empty_pulse(timestamp, sentiment="unknown", error=str(e))
