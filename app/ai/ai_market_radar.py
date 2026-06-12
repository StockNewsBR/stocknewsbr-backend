# =====================================================
# STOCKNEWSBR AI MARKET RADAR
# Ultra Fast Scanner
# =====================================================

import logging

import pandas as pd

from app.ai.ai_radar import run_radar
from app.cache.snapshot_cache import get_snapshot_signals

logger = logging.getLogger("stocknewsbr.market_radar")

MIN_ROWS = 100


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def detect_compression(df):

    try:

        if df is None or len(df) < MIN_ROWS:
            return 0

        high = df["High"]
        low = df["Low"]
        close = df["Close"]
        volume = df["Volume"]

        # -------------------------
        # TRUE RANGE
        # -------------------------

        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)

        atr = tr.rolling(14).mean()
        atr_base = atr.rolling(50).mean().iloc[-1]

        if not atr_base:
            return 0

        atr_ratio = atr.iloc[-1] / atr_base

        # -------------------------
        # NR7
        # -------------------------

        ranges = high - low
        nr7 = ranges.iloc[-1] == ranges.rolling(7).min().iloc[-1]

        # -------------------------
        # VOLUME
        # -------------------------

        vol_avg = volume.rolling(20).mean().iloc[-1]

        if not vol_avg:
            return 0

        vol_ratio = volume.iloc[-1] / vol_avg

        # -------------------------
        # NEAR HIGH
        # -------------------------

        recent_high = close.rolling(20).max().iloc[-2]
        near_high = close.iloc[-1] > recent_high * 0.97

        score = 0

        if atr_ratio < 0.8:
            score += 30

        if nr7:
            score += 25

        if vol_ratio > 1.3:
            score += 25

        if near_high:
            score += 20

        return score

    except Exception:

        logger.exception("Compression detection error")

        return 0


def _normalize_symbol(value):
    return str(value or "").upper().strip().replace(".SA", "").replace("-USD", "USD")


def analyze_symbol(symbol):

    try:
        normalized = _normalize_symbol(symbol)
        rows = [
            row
            for row in get_snapshot_signals()
            if _normalize_symbol(row.get("ticker") or row.get("symbol")) == normalized
        ]

        radar_rows = run_radar(rows, limit=1)

        if not radar_rows:
            return None

        radar = radar_rows[0]
        score = _safe_float(radar.get("score") or radar.get("radar_score") or 0)

        if score < 60:
            return None

        return {
            "symbol": normalized,
            "radar_score": score
        }

    except Exception:

        logger.exception(f"Radar analysis error {symbol}")

        return None


def build_radar():

    results = []

    try:
        for row in run_radar(get_snapshot_signals(), limit=50):
            symbol = row.get("ticker") or row.get("symbol")
            if not symbol:
                continue
            results.append(
                {
                    "symbol": _normalize_symbol(symbol),
                    "radar_score": _safe_float(row.get("score") or row.get("radar_score") or 0),
                    "state": row.get("state"),
                    "source": "snapshot",
                }
            )

    except Exception:

        logger.exception("Radar scanner error")

    results.sort(key=lambda x: x["radar_score"], reverse=True)

    return results
