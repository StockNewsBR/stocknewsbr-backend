# =====================================================
# STOCKNEWSBR ENGINE ORCHESTRATOR
# =====================================================

import logging
import os
import time

from app.cache.signal_cache import get_all_signals, update_signals
from app.data.warm_data_pool import get_market_pool
from app.engine.core.engine_v36 import run_engine as run_engine_v36
from app.engine.core.vector_scanner_engine import vector_scanner_engine
from app.engine.events.price_event_engine import detect_price_events
from app.engine.matrix.build_market_matrices import build_market_matrices
from app.engine.matrix.feature_matrix_engine import feature_matrix_engine
from app.engine.ranking.ranking_engine_v2 import build_ranking
from app.system.observability_engine import record_cycle
from app.system.system_metrics import record_signal_quality_coverage, record_worker_stage_duration

logger = logging.getLogger("stocknewsbr.engine.orchestrator")

ENGINE_MODE = os.getenv("ENGINE_MODE", "AUTO").upper()
EVENT_SCAN_SYMBOLS = max(20, int(os.getenv("EVENT_SCAN_SYMBOLS", "80")))
MARKET_POOL_SOURCE = "warm_market_pool"


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

    def normalize_ticker(value):
        ticker = str(value or "").upper().strip()

        if ticker.endswith(".SA"):
            ticker = ticker[:-3]

        if ticker.endswith("-USD"):
            ticker = ticker[:-4] + "USD"

        return ticker

    for event in events:
        if not isinstance(event, dict):
            continue

        ticker = normalize_ticker(event.get("ticker") or event.get("symbol"))

        if not ticker:
            continue

        events_by_ticker.setdefault(ticker, []).append(dict(event))

    annotated = []

    for row in ranked:
        if not isinstance(row, dict):
            continue

        item = dict(row)
        ticker = item.get("ticker") or item.get("symbol")
        row_events = list(item.get("events", []))
        normalized_ticker = normalize_ticker(ticker)

        if ticker:
            item["ticker"] = ticker
            item["symbol"] = ticker

        if normalized_ticker in events_by_ticker:
            row_events.extend(events_by_ticker[normalized_ticker])

        if row_events:
            item["events"] = row_events

        annotated.append(item)

    return annotated


def _normalize_ticker(value):
    ticker = str(value or "").upper().strip()

    if ticker.endswith(".SA"):
        ticker = ticker[:-3]

    if ticker.endswith("-USD"):
        ticker = ticker[:-4] + "USD"

    return ticker


def _pool_lookup(pool):
    index = {}

    for key, frame in (pool or {}).items():
        raw = str(key or "").upper().strip()
        if not raw:
            continue

        index.setdefault(raw, frame)
        index.setdefault(_normalize_ticker(raw), frame)

    return index


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        number = float(value)
        if number != number:
            return default
        return number
    except Exception:
        return default


def _int_if_whole(value):
    number = _safe_float(value)
    if number is None:
        return None
    if number >= 0 and number.is_integer():
        return int(number)
    return number


def _latest_market_row(frame):
    try:
        columns = getattr(frame, "columns", [])
        if "Close" not in columns:
            return None, None, None

        data = frame.dropna(how="all")
        close = data["Close"].dropna()

        if len(close) == 0:
            return None, None, None

        last_index = close.index[-1]
        latest = data.loc[last_index]
        return data, close, latest
    except Exception:
        return None, None, None


def _frame_value(latest, column):
    try:
        return _safe_float(latest.get(column))
    except Exception:
        return None


def _market_stamp(value):
    try:
        if hasattr(value, "isoformat"):
            return value.isoformat()
    except Exception:
        pass
    return str(value) if value is not None else None


def _compute_vwap(data):
    try:
        required = {"High", "Low", "Close", "Volume"}
        if not required.issubset(set(getattr(data, "columns", []))):
            return None

        recent = data[list(required)].dropna().tail(20)
        if len(recent) == 0:
            return None

        volume = recent["Volume"].astype(float)
        volume_sum = float(volume.sum())
        if volume_sum <= 0:
            return None

        typical = (recent["High"].astype(float) + recent["Low"].astype(float) + recent["Close"].astype(float)) / 3.0
        return float((typical * volume).sum() / volume_sum)
    except Exception:
        return None


def _enrich_row_with_market_data(row, frame):
    item = dict(row)
    data, close, latest = _latest_market_row(frame)

    if data is None or close is None or latest is None:
        item.setdefault("data_quality", "score_only")
        return item

    price = _frame_value(latest, "Close")
    volume = _frame_value(latest, "Volume")

    if price is None or price <= 0 or volume is None or volume <= 0:
        item.setdefault("data_quality", "score_only")
        return item

    prev_close = _safe_float(close.iloc[-2] if len(close) >= 2 else price, price)
    avg_volume = None
    try:
        volume_series = data["Volume"].dropna().tail(20).astype(float)
        if len(volume_series):
            avg_volume = float(volume_series.mean())
    except Exception:
        avg_volume = None

    rel_volume = (volume / avg_volume) if avg_volume and avg_volume > 0 else 0.0
    change_pct = ((price - prev_close) / prev_close * 100.0) if prev_close else 0.0

    market_fields = {
        "price": round(price, 6),
        "close": round(price, 6),
        "prev_close": round(prev_close, 6),
        "volume": _int_if_whole(volume),
        "avg_volume": int(avg_volume) if avg_volume is not None else None,
        "rel_volume": round(rel_volume, 4),
        "change_pct": round(change_pct, 4),
        "data_quality": "priced",
        "price_source": MARKET_POOL_SOURCE,
        "volume_source": MARKET_POOL_SOURCE,
        "market_data_points": int(len(data)),
        "market_data_updated_at": _market_stamp(getattr(latest, "name", None)),
    }

    for target, source in (("open", "Open"), ("high", "High"), ("low", "Low")):
        value = _frame_value(latest, source)
        if value is not None:
            market_fields[target] = round(value, 6)

    vwap = _compute_vwap(data)
    if vwap is not None:
        market_fields["vwap"] = round(vwap, 6)

    return {**item, **{key: value for key, value in market_fields.items() if value is not None}}


def _enrich_ranked_with_market_data(ranked, pool):
    if not ranked:
        return []

    lookup = _pool_lookup(pool)
    enriched = []

    for row in ranked:
        if not isinstance(row, dict):
            continue

        ticker = row.get("ticker") or row.get("symbol")
        frame = lookup.get(str(ticker or "").upper().strip())
        if frame is None:
            frame = lookup.get(_normalize_ticker(ticker))

        if frame is None:
            item = dict(row)
            item.setdefault("data_quality", "score_only")
            enriched.append(item)
            continue

        enriched.append(_enrich_row_with_market_data(row, frame))

    return enriched


def run_engine():
    start = time.perf_counter()

    try:
        pool_start = time.perf_counter()
        pool = _safe_run(get_market_pool)
        record_worker_stage_duration("market_pool", time.perf_counter() - pool_start, success=bool(pool))

        if not pool:
            record_cycle(time.perf_counter() - start, 0)
            return []

        ranked = []
        ranking_start = time.perf_counter()

        if ENGINE_MODE in ("AUTO", "V36"):
            ranked = _safe_run(run_engine_v36, pool) or []

        if not ranked:
            ranked = _run_legacy(pool)
        record_worker_stage_duration("ranking", time.perf_counter() - ranking_start, success=bool(ranked))

        if not ranked:
            cached = get_all_signals()
            if cached:
                logger.warning(
                    "Engine returned empty result; reusing cached signals | count=%s",
                    len(cached),
                )
                elapsed = time.perf_counter() - start
                _safe_run(record_cycle, elapsed, len(cached))
                return cached

            record_cycle(time.perf_counter() - start, 0)
            return []

        event_start = time.perf_counter()
        events = _safe_run(detect_price_events, pool, ranked, EVENT_SCAN_SYMBOLS) or []
        record_worker_stage_duration("event_detection", time.perf_counter() - event_start, success=True)
        ranked = _attach_events(ranked, events)
        ranked = _enrich_ranked_with_market_data(ranked, pool)
        _safe_run(record_signal_quality_coverage, ranked, source="signal_cache")
        _safe_run(update_signals, ranked)

        elapsed = time.perf_counter() - start
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
