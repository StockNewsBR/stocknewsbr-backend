from __future__ import annotations

from datetime import time as dtime
from typing import Dict, Iterable, List
from zoneinfo import ZoneInfo

import pandas as pd


B3_TIMEZONE = ZoneInfo("America/Sao_Paulo")
B3_OPEN = dtime(10, 0)
B3_CLOSE = dtime(17, 55)
FRAME_LOOKBACK = 96
EVENT_SCAN_BARS = 18
DEFAULT_MAX_EVENT_SYMBOLS = 80


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return default


def _canonical_symbol(value: str | None) -> str:
    symbol = str(value or "").upper().strip()

    if symbol.endswith(".SA"):
        symbol = symbol[:-3]

    if symbol.endswith("-USD"):
        symbol = symbol[:-4] + "USD"

    return symbol


def _display_symbol(value: str | None) -> str:
    return _canonical_symbol(value)


def _is_b3_symbol(value: str | None) -> bool:
    return str(value or "").upper().strip().endswith(".SA")


def _to_timestamp(value):
    try:
        timestamp = pd.Timestamp(value)
    except Exception:
        return None

    if timestamp.tzinfo is None:
        try:
            timestamp = timestamp.tz_localize("UTC")
        except Exception:
            return None

    return timestamp


def _is_regular_session(symbol: str | None, timestamp) -> bool:
    if not _is_b3_symbol(symbol):
        return True

    stamp = _to_timestamp(timestamp)

    if stamp is None:
        return False

    local = stamp.tz_convert(B3_TIMEZONE)

    if local.weekday() >= 5:
        return False

    current_time = local.timetz().replace(tzinfo=None)
    return B3_OPEN <= current_time <= B3_CLOSE


def _build_ranked_lookup(ranked_rows: Iterable[dict] | None) -> Dict[str, dict]:
    lookup: Dict[str, dict] = {}

    for row in ranked_rows or []:
        if not isinstance(row, dict):
            continue

        key = _canonical_symbol(row.get("ticker") or row.get("symbol"))

        if key:
            lookup[key] = dict(row)

    return lookup


def _prepare_frame(frame) -> pd.DataFrame:
    if frame is None or getattr(frame, "empty", True):
        return pd.DataFrame()

    columns = ["Open", "High", "Low", "Close", "Volume"]

    try:
        df = frame[columns].copy()
    except Exception:
        return pd.DataFrame()

    df = df.tail(FRAME_LOOKBACK).dropna(subset=["Open", "High", "Low", "Close"])

    if len(df) < 24:
        return pd.DataFrame()

    close = pd.to_numeric(df["Close"], errors="coerce")
    high = pd.to_numeric(df["High"], errors="coerce")
    low = pd.to_numeric(df["Low"], errors="coerce")
    volume = pd.to_numeric(df["Volume"], errors="coerce").fillna(0)

    df["ema9"] = close.ewm(span=9, adjust=False).mean()
    df["ema21"] = close.ewm(span=21, adjust=False).mean()
    df["volume_avg"] = volume.rolling(20, min_periods=5).mean()
    df["rel_volume"] = volume / df["volume_avg"].replace(0, pd.NA)
    df["breakout_high"] = high.shift(1).rolling(12, min_periods=5).max()
    df["breakdown_low"] = low.shift(1).rolling(12, min_periods=5).min()
    df["close_pct_change"] = close.pct_change().fillna(0.0) * 100
    df["close"] = close
    return df.dropna(subset=["ema9", "ema21", "breakout_high", "breakdown_low"])


def _event_payload(symbol: str, row, event_type: str, strength: float, reason: str) -> dict:
    price = _safe_float(row.get("close"))
    change_pct = _safe_float(row.get("close_pct_change"))

    return {
        "ticker": _display_symbol(symbol),
        "symbol": _display_symbol(symbol),
        "type": event_type,
        "side": "buy" if event_type in {"BUY", "COVER"} else "sell",
        "price": round(price, 4),
        "time": str(row.name),
        "change": round(change_pct / 100.0, 6),
        "change_pct": round(change_pct, 4),
        "strength": int(max(1, min(round(strength), 100))),
        "reason": reason,
        "source": "price_event_engine",
    }


def _scan_frame(symbol: str, frame: pd.DataFrame, ranked_row: dict | None = None) -> List[dict]:
    df = _prepare_frame(frame)

    if df.empty:
        return []

    score = _safe_float((ranked_row or {}).get("score"))
    trend = str((ranked_row or {}).get("trend") or "").lower()
    prefer_long = score >= 55 or trend in {"alta", "up", "bullish", "bull"}
    prefer_short = score <= 45 or trend in {"baixa", "down", "bearish", "bear"}

    events: List[dict] = []
    position = None

    for _, row in df.tail(EVENT_SCAN_BARS).iterrows():
        volume_rel = _safe_float(row.get("rel_volume"), 1.0)
        ema9 = _safe_float(row.get("ema9"))
        ema21 = _safe_float(row.get("ema21"))
        close = _safe_float(row.get("close"))
        breakout_high = _safe_float(row.get("breakout_high"))
        breakdown_low = _safe_float(row.get("breakdown_low"))
        change_pct = _safe_float(row.get("close_pct_change"))

        bullish_breakout = (
            close > breakout_high
            and ema9 > ema21
            and volume_rel >= 1.05
            and change_pct >= 0
        )
        bearish_breakdown = (
            close < breakdown_low
            and ema9 < ema21
            and volume_rel >= 1.05
            and change_pct <= 0
        )
        long_exit = position == "long" and (close < ema21 or ema9 < ema21)
        short_exit = position == "short" and (close > ema21 or ema9 > ema21)

        if bullish_breakout and position != "long" and (prefer_long or not prefer_short):
            if _is_regular_session(symbol, row.name):
                strength = 55 + min(35, (volume_rel - 1.0) * 22) + min(10, score / 20)
                events.append(_event_payload(symbol, row, "BUY", strength, "breakout_with_volume"))
                position = "long"
            continue

        if bearish_breakdown and position != "short" and (prefer_short or not prefer_long):
            if _is_regular_session(symbol, row.name):
                strength = 55 + min(35, (volume_rel - 1.0) * 22) + min(10, (100 - score) / 20)
                events.append(_event_payload(symbol, row, "SHORT", strength, "breakdown_with_volume"))
                position = "short"
            continue

        if long_exit and _is_regular_session(symbol, row.name):
            events.append(_event_payload(symbol, row, "SELL", 52, "trend_loss"))
            position = None
            continue

        if short_exit and _is_regular_session(symbol, row.name):
            events.append(_event_payload(symbol, row, "COVER", 52, "trend_loss"))
            position = None

    return events[-6:]


def detect_price_events(
    pool: Dict[str, object],
    ranked_rows: Iterable[dict] | None = None,
    max_symbols: int = DEFAULT_MAX_EVENT_SYMBOLS,
) -> List[dict]:
    if not isinstance(pool, dict) or not pool:
        return []

    ranked_lookup = _build_ranked_lookup(ranked_rows)
    events: List[dict] = []
    candidate_symbols: List[tuple[str, object, dict | None]] = []
    pool_by_symbol = {
        _canonical_symbol(symbol): (symbol, frame)
        for symbol, frame in pool.items()
        if _canonical_symbol(symbol)
    }

    if ranked_lookup:
        for ranked_row in ranked_rows or []:
            if not isinstance(ranked_row, dict):
                continue

            ticker = _canonical_symbol(ranked_row.get("ticker") or ranked_row.get("symbol"))

            if not ticker:
                continue

            pool_entry = pool_by_symbol.get(ticker)
            if pool_entry:
                symbol, frame = pool_entry
                candidate_symbols.append((symbol, frame, ranked_lookup.get(ticker)))
    else:
        candidate_symbols = [(symbol, frame, None) for symbol, frame in pool.items()]

    if max_symbols > 0:
        candidate_symbols = candidate_symbols[:max_symbols]

    for symbol, frame, ranked_row in candidate_symbols:
        events.extend(_scan_frame(symbol, frame, ranked_row))

    return events
