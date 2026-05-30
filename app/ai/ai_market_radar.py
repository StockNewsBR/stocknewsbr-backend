# =====================================================
# STOCKNEWSBR AI MARKET RADAR
# Ultra Fast Scanner
# =====================================================

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf
import pandas as pd

from app.config import SYMBOLS

logger = logging.getLogger("stocknewsbr.market_radar")

MAX_WORKERS = 8
MIN_ROWS = 100


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


def analyze_symbol(symbol):

    try:

        df = yf.download(
            symbol,
            period="10d",
            interval="15m",
            progress=False,
            auto_adjust=True,
            threads=False,
            timeout=8,
        )

        if df is None or len(df) < MIN_ROWS:
            return None

        score = detect_compression(df)

        if score < 60:
            return None

        return {
            "symbol": symbol.replace(".SA", ""),
            "radar_score": score
        }

    except Exception:

        logger.exception(f"Radar analysis error {symbol}")

        return None


def build_radar():

    results = []

    try:

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

            futures = [executor.submit(analyze_symbol, s) for s in SYMBOLS]

            for future in as_completed(futures):

                result = future.result()

                if result:
                    results.append(result)

    except Exception:

        logger.exception("Radar scanner error")

    results.sort(key=lambda x: x["radar_score"], reverse=True)

    return results
