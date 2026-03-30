# =====================================================
# STOCKNEWSBR ENGINE ORCHESTRATOR
# =====================================================

import logging
import os
import time

from app.cache.signal_cache import update_signals
from app.data.warm_data_pool import get_market_pool
from app.engine.core.engine_v36 import run_engine as run_engine_v36
from app.engine.core.vector_scanner_engine import vector_scanner_engine
from app.engine.events.price_event_engine import detect_price_events
from app.engine.matrix.build_market_matrices import build_market_matrices
from app.engine.matrix.feature_matrix_engine import feature_matrix_engine
from app.engine.ranking.ranking_engine_v2 import build_ranking
from app.system.observability_engine import record_cycle

logger = logging.getLogger("stocknewsbr.engine.orchestrator")

ENGINE_MODE = os.getenv("ENGINE_MODE", "AUTO").upper()


def _safe_run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        logger.exception("Engine step failed: %s", exc)
        return None


def _run_legacy(pool):
    matrices = _safe_run(build_market_matrices, pool)

    if not matrices:
        return []

    price_matrix = matrices.get("price_matrix")
    volume_matrix = matrices.get("volume_matrix")

    if price_matrix is None or volume_matrix is None:
        return []

    features = _safe_run(
        feature_matrix_engine.compute,
        price_matrix,
        volume_matrix,
    )

    if not features:
        return []

    signals = _safe_run(
        vector_scanner_engine.run,
        features,
        matrices,
    )

    if not signals:
        return []

    return _safe_run(build_ranking, signals) or []


def _attach_events(ranked, events):
    if not ranked:
        return []

    if not events:
        return ranked

    events_by_ticker = {}

    for event in events:
        if not isinstance(event, dict):
            continue

        ticker = event.get("ticker")

        if not ticker:
            continue

        events_by_ticker.setdefault(ticker, []).append(
            {
                "type": "price_event",
                "price": event.get("price"),
                "change": event.get("change"),
            }
        )

    annotated = []

    for row in ranked:
        if not isinstance(row, dict):
            continue

        item = dict(row)
        ticker = item.get("ticker") or item.get("symbol")
        row_events = list(item.get("events", []))

        if ticker:
            item["ticker"] = ticker
            item["symbol"] = ticker

        if ticker in events_by_ticker:
            row_events.extend(events_by_ticker[ticker])

        if row_events:
            item["events"] = row_events

        annotated.append(item)

    return annotated


def run_engine():
    start = time.time()

    try:
        pool = _safe_run(get_market_pool)

        if not pool:
            record_cycle(time.time() - start, 0)
            return []

        events = _safe_run(detect_price_events, pool) or []
        ranked = []

        if ENGINE_MODE in ("AUTO", "V36"):
            ranked = _safe_run(run_engine_v36) or []

        if not ranked:
            ranked = _run_legacy(pool)

        if not ranked:
            record_cycle(time.time() - start, 0)
            return []

        ranked = _attach_events(ranked, events)
        _safe_run(update_signals, ranked)

        elapsed = time.time() - start
        _safe_run(record_cycle, elapsed, len(ranked))

        logger.info(
            "Engine cycle completed | signals=%s | time=%.4fs",
            len(ranked),
            elapsed,
        )

        return ranked

    except Exception as exc:
        logger.exception("Engine orchestrator crash: %s", exc)
        record_cycle(time.time() - start, 0)
        return []
