import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.config import SYMBOLS, UPDATE_INTERVAL

# IA modules
from app.ai_market_radar import build_radar
from app.liquidity_sweep import build_sweep
from app.liquidity_map import liquidity_zones

# AI metrics
from app.ai_confidence import calculate_confidence
from app.ai_confluence import calculate_confluence
from app.ai_signal_strength import calculate_signal_strength
from app.ai_market_narrative import generate_market_narrative


MAX_WORKERS = 8


CACHE = {}
LAST_UPDATE = None


# =========================================================
# INDICATORS
# =========================================================

def calculate_indicators(df):

    close = df["Close"]
    volume = df["Volume"]

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    ema21 = close.ewm(span=21).mean()
    ema50 = close.ewm(span=50).mean()
    ema200 = close.ewm(span=200).mean()

    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()

    macd = ema12 - ema26

    roc = close.pct_change(12) * 100

    avg_volume = volume.rolling(20).mean()
    volume_ratio = volume / avg_volume

    breakout = close.iloc[-1] > close.rolling(20).max().iloc[-2]

    return {
        "rsi": float(rsi.iloc[-1]),
        "ema21": float(ema21.iloc[-1]),
        "ema50": float(ema50.iloc[-1]),
        "ema200": float(ema200.iloc[-1]),
        "macd": float(macd.iloc[-1]),
        "roc": float(roc.iloc[-1]),
        "volume_ratio": float(volume_ratio.iloc[-1]),
        "breakout": bool(breakout)
    }


# =========================================================
# SCORE
# =========================================================

def calculate_score(symbol):

    try:

        df = yf.download(
            symbol,
            period="5d",
            interval="15m",
            auto_adjust=True,
            progress=False
        )

        if df is None or df.empty:
            return None

        ind = calculate_indicators(df)

        score = 0

        if ind["ema21"] > ind["ema50"] > ind["ema200"]:
            score += 20

        if 55 < ind["rsi"] < 70:
            score += 15

        if ind["macd"] > 0:
            score += 15

        if ind["roc"] > 0:
            score += 10

        if ind["volume_ratio"] > 1.5:
            score += 20

        if ind["breakout"]:
            score += 20

        trend = "UPTREND" if ind["ema21"] > ind["ema50"] else "DOWNTREND"

        # =================================================
        # AI METRICS
        # =================================================

        active_models = 8

        confluence = calculate_confluence(active_models)
        confidence = calculate_confidence(score)
       
        signal_strength = calculate_signal_strength(score, confluence)

        narrative = generate_market_narrative(symbol, score, confluence)

        return {
            "symbol": symbol,
            "score": score,
            "trend": trend,
            "volume_spike": round(ind["volume_ratio"], 2),

            "ai_confluence": confluence,
            "ai_confidence": confidence,
            "signal_strength": signal_strength,
            "ai_narrative": narrative
        }

    except Exception as e:

        print("Erro:", symbol, e)
        return None


# =========================================================
# PARALLEL SCANNER
# =========================================================

def scan_symbol(symbol):

    return calculate_score(symbol)


def scan_market_parallel():

    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

        futures = [executor.submit(scan_symbol, symbol) for symbol in SYMBOLS]

        for future in as_completed(futures):

            result = future.result()

            if result:
                results.append(result)

    return results


# =========================================================
# ENGINE UPDATE
# =========================================================

def update_cache():

    global CACHE, LAST_UPDATE

    print(f"⚡ Engine scanning {len(SYMBOLS)} ativos...")

    results = scan_market_parallel()

    if results:

        results.sort(
            key=lambda x: (x["score"], x["volume_spike"]),
            reverse=True
        )

        CACHE = {item["symbol"]: item for item in results}

        LAST_UPDATE = datetime.now().strftime("%H:%M:%S")

        print("✅ Ranking updated:", LAST_UPDATE)

    try:

        radar = build_radar()
        sweep = build_sweep()

        print("Radar signals:", len(radar))
        print("Liquidity sweeps:", len(sweep))

    except Exception as e:

        print("AI module error:", e)


# =========================================================
# AUTO LOOP
# =========================================================

def auto_update():

    while True:

        update_cache()

        time.sleep(UPDATE_INTERVAL)


# =========================================================
# PUBLIC API
# =========================================================

def scan_market():

    return list(CACHE.values())


def collect_market_signals():

    signals = []

    for item in CACHE.values():

        if item.get("trend") == "UPTREND":
            signals.append("bullish")
        else:
            signals.append("bearish")

    return signals