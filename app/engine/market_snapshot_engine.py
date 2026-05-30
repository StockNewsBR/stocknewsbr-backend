# =====================================================
# MARKET SNAPSHOT ENGINE
# =====================================================

import logging
from datetime import datetime, timezone

import pandas as pd

from app.ai.feature_hub import build_ai_tool_payload
from app.ai.trade_decision import summarize_trade_decision
from app.cache.signal_cache import get_all_signals
from app.cache.snapshot_cache import get_last_good_snapshot, get_snapshot, update_snapshot
from app.data.warm_data_pool import get_market_pool
from app.engine.engine_orchestrator import run_engine
from app.engine.indicators.vector_indicator_engine import compute_rsi
from app.services.signal_history import store_signals
from app.system.system_metrics import record_signal_quality_coverage

logger = logging.getLogger("stocknewsbr.snapshot_engine")
AI_INPUT_LIMIT = 80
AI_OUTPUT_LIMIT = 20
LAST_GOOD_SIGNAL_LIMIT = 200
_FEATURE_SEED_FIELDS = {
    "price",
    "volume",
    "rsi",
    "adx",
    "atr_pct",
    "bb_width",
    "kc_width",
    "momentum",
    "change_pct",
    "market_data_updated_at",
}


def _safe_score(row):
    try:
        return float(row.get("score", 0) or 0)
    except Exception:
        return 0.0


def _normalize_pool_key(value: str | None) -> str:
    ticker = str(value or "").upper().strip()

    if not ticker:
        return ticker

    if ticker.endswith(".SA"):
        return ticker

    if ticker.endswith("USD") and "-" not in ticker:
        return ticker[:-3] + "-USD"

    if "." not in ticker and "-" not in ticker and ticker.endswith(("3", "4", "5", "6", "11", "34")):
        return f"{ticker}.SA"

    return ticker


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _has_positive_value(row, *keys: str) -> bool:
    for key in keys:
        if _safe_float(row.get(key), 0.0) > 0:
            return True
    return False


def _apply_data_quality(row):
    item = dict(row)
    if _has_positive_value(item, "price", "close", "last_price") and _has_positive_value(item, "volume", "last_volume"):
        item["data_quality"] = item.get("data_quality") or "priced"
    else:
        item["data_quality"] = "score_only"
    return item


def _latest_or_default(series, default: float = 0.0) -> float:
    try:
        if series is None or len(series) == 0:
            return default
        value = series.iloc[-1]
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _build_feature_seed(ticker: str, frame, signal_row):
    if frame is None or frame.empty:
        return dict(signal_row)

    try:
        data = frame.tail(80).copy().dropna(how="all")

        if len(data) < 20:
            return dict(signal_row)

        close = data["Close"].astype(float).dropna()
        high = data["High"].astype(float).dropna()
        low = data["Low"].astype(float).dropna()
        open_ = data["Open"].astype(float).dropna()
        volume = data["Volume"].astype(float).fillna(0.0)

        if len(close) < 20:
            return dict(signal_row)

        market_data_updated_at = None
        try:
            last_index = close.index[-1]
            if hasattr(last_index, "isoformat"):
                market_data_updated_at = last_index.isoformat()
            elif last_index is not None:
                market_data_updated_at = str(last_index)
        except Exception:
            market_data_updated_at = None

        price = _latest_or_default(close)
        prev_close = _latest_or_default(close.iloc[:-1], price)
        open_price = _latest_or_default(open_, price)
        high_price = _latest_or_default(high, price)
        low_price = _latest_or_default(low, price)
        last_volume = _latest_or_default(volume, 0.0)
        avg_volume = float(volume.tail(20).mean()) if len(volume) >= 20 else float(volume.mean())
        rel_volume = (last_volume / avg_volume) if avg_volume > 0 else 0.0
        change_pct = ((price - prev_close) / prev_close * 100.0) if prev_close else 0.0

        typical_price = (high.tail(20) + low.tail(20) + close.tail(20)) / 3.0
        typical_volume = volume.tail(20)
        volume_sum = float(typical_volume.sum())
        vwap = float((typical_price * typical_volume).sum() / volume_sum) if volume_sum > 0 else price

        rsi = _latest_or_default(compute_rsi(close), 50.0)

        prev_close_series = close.shift(1).fillna(close)
        true_range = pd.concat(
            [
                (high - low).abs(),
                (high - prev_close_series).abs(),
                (low - prev_close_series).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = float(true_range.tail(14).mean()) if len(true_range) >= 14 else float(true_range.mean())
        atr_pct = (atr / price * 100.0) if price > 0 else 0.0

        ema20 = close.ewm(span=20, adjust=False).mean()
        mid20 = _latest_or_default(ema20, price)
        std20 = float(close.tail(20).std()) if len(close) >= 20 else 0.0
        bb_width = ((4.0 * std20) / mid20) if mid20 > 0 else 0.0
        kc_width = ((4.0 * atr) / mid20) if mid20 > 0 else 0.0

        five_back = _safe_float(close.iloc[-6], price) if len(close) >= 6 else prev_close
        twenty_back = _safe_float(close.iloc[-21], price) if len(close) >= 21 else prev_close
        momentum = ((price - five_back) / five_back * 100.0) if five_back else 0.0
        trend_20 = ((price - twenty_back) / twenty_back * 100.0) if twenty_back else 0.0

        recent_returns = close.pct_change().dropna().tail(14)
        positive_days = int((recent_returns > 0).sum()) if len(recent_returns) else 0
        directional_persistence = (positive_days / max(1, len(recent_returns)))
        adx_proxy = 10.0 + abs(trend_20) * 2.6 + max(rel_volume - 1.0, 0.0) * 8.0 + directional_persistence * 18.0
        adx_proxy = max(10.0, min(45.0, adx_proxy))

        enriched = dict(signal_row)
        enriched.update(
            {
                "ticker": ticker,
                "symbol": ticker,
                "price": round(price, 6),
                "prev_close": round(prev_close, 6),
                "open": round(open_price, 6),
                "high": round(high_price, 6),
                "low": round(low_price, 6),
                "volume": int(last_volume),
                "avg_volume": int(avg_volume),
                "rel_volume": round(rel_volume, 4),
                "vwap": round(vwap, 6),
                "rsi": round(rsi, 4),
                "adx": round(adx_proxy, 4),
                "atr_pct": round(atr_pct, 4),
                "bb_width": round(bb_width, 6),
                "kc_width": round(kc_width, 6),
                "momentum": round(momentum, 4),
                "change_pct": round(change_pct, 4),
                "data_quality": "priced" if price > 0 and last_volume > 0 else "score_only",
                "market_data_updated_at": market_data_updated_at,
                "last_bar_at": market_data_updated_at,
                "feature_confidence": 92,
                "trend": signal_row.get("trend", trend_20),
            }
        )
        return enriched
    except Exception:
        logger.exception("Snapshot feature enrichment failed for %s", ticker)
        return dict(signal_row)


def _enrich_signal_rows(signals):
    rows = [dict(row) for row in signals or [] if isinstance(row, dict)]
    if not rows:
        return []

    if all(_has_positive_value(row, "price", "close", "last_price") and _has_positive_value(row, "volume", "last_volume") for row in rows):
        return [_apply_data_quality(row) for row in rows]

    if all(_FEATURE_SEED_FIELDS.issubset(row.keys()) for row in rows):
        return rows

    pool = get_market_pool()

    if not pool:
        return rows

    enriched = []
    pool_keys = {str(key).upper().strip(): value for key, value in pool.items()}

    for row in rows:
        ticker = str(row.get("ticker") or row.get("symbol") or "").upper().strip()
        frame = pool_keys.get(ticker)

        if frame is None:
            frame = pool_keys.get(_normalize_pool_key(ticker))

        if frame is None:
            enriched.append(dict(row))
            continue

        enriched.append(_build_feature_seed(ticker or _normalize_pool_key(ticker), frame, row))

    return enriched


def build_snapshot_payload(signals, source: str = "engine", stale: bool = False):
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
        item = _apply_data_quality(item)
        normalized.append(item)

    normalized.sort(key=_safe_score, reverse=True)
    record_signal_quality_coverage(normalized, source=f"snapshot:{source}")

    bullish = len([row for row in normalized if row["score"] >= 70])
    bearish = len([row for row in normalized if row["score"] <= 30])
    ai_input_rows = _enrich_signal_rows(normalized[:AI_INPUT_LIMIT])

    try:
        ai_tools = build_ai_tool_payload(
            top_signals=ai_input_rows,
            ranking=ai_input_rows,
            limit=AI_OUTPUT_LIMIT,
        )
    except Exception:
        logger.exception("Snapshot AI payload build failed")
        ai_tools = {}

    decision = summarize_trade_decision(ai_tools.get("master_score", []))
    logger.info(
        "Snapshot decision | action=%s | confidence=%.1f | regime=%s | source=%s | stale=%s",
        decision.get("trade_action"),
        float(decision.get("trade_confidence", 0.0) or 0.0),
        decision.get("market_regime_state"),
        source,
        stale,
    )

    return {
        "signals": normalized[:200],
        "leaders": normalized[:20],
        "ai_tools": ai_tools,
        "decision": decision,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "stale": bool(stale),
        "stats": {
            "total_signals": len(normalized),
            "bullish": bullish,
            "bearish": bearish,
        },
    }


def _get_last_good_signals():
    snapshot = get_last_good_snapshot() or get_snapshot()
    snapshot_signals = snapshot.get("signals", [])

    if isinstance(snapshot_signals, list) and snapshot_signals:
        return snapshot_signals[:LAST_GOOD_SIGNAL_LIMIT]

    return []


def generate_market_snapshot(signals=None, reuse_last_good_on_empty: bool = True):
    snapshot_source = "signal_argument" if signals is not None else "signal_cache"
    snapshot_stale = False

    try:
        if signals is not None:
            signal_rows = list(signals or [])
            if not signal_rows and reuse_last_good_on_empty:
                signal_rows = _get_last_good_signals()
                snapshot_source = "snapshot_fallback"
                snapshot_stale = bool(signal_rows)
        else:
            signal_rows = get_all_signals()

        if signals is None and not signal_rows:
            snapshot_source = "engine"
            signal_rows = run_engine()

        explicit_empty_request = signals is not None and not signal_rows and not reuse_last_good_on_empty
        if explicit_empty_request:
            payload = build_snapshot_payload([], source="empty", stale=True)
            update_snapshot(payload)
            return payload

        if not signal_rows:
            signal_rows = _get_last_good_signals()
            snapshot_source = "snapshot_fallback"
            snapshot_stale = bool(signal_rows)

        if not signal_rows:
            payload = build_snapshot_payload([], source="empty", stale=True)
            update_snapshot(payload)
            return payload

        store_signals(signal_rows)

        payload = build_snapshot_payload(
            signal_rows,
            source=snapshot_source,
            stale=snapshot_stale,
        )
        update_snapshot(payload)

        return payload

    except Exception as exc:
        logger.exception("Snapshot engine error: %s", exc)
        fallback_rows = _get_last_good_signals()

        if fallback_rows:
            payload = build_snapshot_payload(
                fallback_rows,
                source="exception_fallback",
                stale=True,
            )
            update_snapshot(payload)
            return payload

        return build_snapshot_payload([], source="exception", stale=True)
