# =====================================================
# MARKET SNAPSHOT ENGINE
# =====================================================

import logging
from datetime import datetime, timezone

from app.cache.signal_cache import get_all_signals
from app.cache.snapshot_cache import update_snapshot
from app.engine.engine_orchestrator import run_engine
from app.services.signal_history import store_signals

logger = logging.getLogger("stocknewsbr.snapshot_engine")


def _safe_score(row):
    try:
        return float(row.get("score", 0) or 0)
    except Exception:
        return 0.0


def build_snapshot_payload(signals):
    normalized = []

    for row in signals or []:
        if not isinstance(row, dict):
            continue

        item = dict(row)
        ticker = item.get("ticker") or item.get("symbol")

        if ticker:
            item["ticker"] = ticker
            item["symbol"] = ticker

        item["score"] = _safe_score(item)
        normalized.append(item)

    normalized.sort(key=_safe_score, reverse=True)

    bullish = len([row for row in normalized if row["score"] >= 70])
    bearish = len([row for row in normalized if row["score"] <= 30])

    return {
        "signals": normalized[:200],
        "leaders": normalized[:20],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_signals": len(normalized),
            "bullish": bullish,
            "bearish": bearish,
        },
    }


def generate_market_snapshot(signals=None):
    try:
        signal_rows = signals if signals is not None else get_all_signals()

        if not signal_rows:
            signal_rows = run_engine()

        if not signal_rows:
            payload = build_snapshot_payload([])
            update_snapshot(payload)
            return payload

        store_signals(signal_rows)

        payload = build_snapshot_payload(signal_rows)
        update_snapshot(payload)

        return payload

    except Exception as exc:
        logger.exception("Snapshot engine error: %s", exc)
        return build_snapshot_payload([])
