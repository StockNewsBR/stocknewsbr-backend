# =====================================================
# MARKET SNAPSHOT ENGINE
# =====================================================

import logging
from datetime import datetime, timezone

from app.ai.feature_hub import build_ai_tool_payload
from app.cache.signal_cache import get_all_signals
from app.cache.snapshot_cache import update_snapshot
from app.engine.engine_orchestrator import run_engine
from app.services.signal_history import store_signals

logger = logging.getLogger("stocknewsbr.snapshot_engine")
AI_INPUT_LIMIT = 80
AI_OUTPUT_LIMIT = 20


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
    ai_input_rows = normalized[:AI_INPUT_LIMIT]

    try:
        ai_tools = build_ai_tool_payload(
            top_signals=ai_input_rows,
            ranking=ai_input_rows,
            limit=AI_OUTPUT_LIMIT,
        )
    except Exception:
        logger.exception("Snapshot AI payload build failed")
        ai_tools = {}

    return {
        "signals": normalized[:200],
        "leaders": normalized[:20],
        "ai_tools": ai_tools,
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
