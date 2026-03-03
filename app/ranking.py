from fastapi import APIRouter, Depends
import yfinance as yf
import pandas as pd
import numpy as np

from app.dependencies import require_active_plan
from app.config import SYMBOLS

router = APIRouter(
    prefix="/ranking",
    tags=["Ranking"]
)

# =====================================================
# INDICADORES MANUAIS
# =====================================================

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def calculate_macd(series):
    ema12 = calculate_ema(series, 12)
    ema26 = calculate_ema(series, 26)
    macd = ema12 - ema26
    signal = calculate_ema(macd, 9)
    return macd, signal


# =====================================================
# SCORE ENGINE
# =====================================================

def calculate_score(symbol: str):
    try:
        df = yf.download(symbol, period="5d", interval="5m", progress=False)

        if df.empty:
            return None

        close = df["Close"]

        rsi_series = calculate_rsi(close)
        rsi = rsi_series.iloc[-1]

        macd, macd_signal = calculate_macd(close)
        macd_value = macd.iloc[-1]
        macd_signal_value = macd_signal.iloc[-1]

        ema9 = calculate_ema(close, 9).iloc[-1]
        ema21 = calculate_ema(close, 21).iloc[-1]

        score = 0

        # RSI
        if rsi < 30:
            score += 25
        elif rsi < 50:
            score += 15
        elif rsi > 70:
            score -= 10

        # MACD
        if macd_value > macd_signal_value:
            score += 25
        else:
            score -= 10

        # Tendência
        if ema9 > ema21:
            score += 25
            trend = "UPTREND"
        else:
            score -= 10
            trend = "DOWNTREND"

        # Volume
        volume_mean = df["Volume"].rolling(20).mean().iloc[-1]
        if df["Volume"].iloc[-1] > volume_mean:
            score += 25

        return {
            "symbol": symbol,
            "score": max(score, 0),
            "trend": trend,
            "rsi": round(float(rsi), 2),
            "breakout": ema9 > ema21
        }

 except Exception as e:
    print(f"Erro em {symbol}: {e}")
    return None


# =====================================================
# ENDPOINT: /ranking
# =====================================================

@router.get("")
def get_ranking(current_user=Depends(require_active_plan)):

    results = []

    for symbol in SYMBOLS:
        data = calculate_score(symbol)
        if data:
            results.append(data)

    results.sort(key=lambda x: x["score"], reverse=True)

    return {"data": results}


# =====================================================
# ENDPOINT: /ranking/top
# =====================================================

@router.get("/top")
def get_top(min_score: int = 50, current_user=Depends(require_active_plan)):

    results = []

    for symbol in SYMBOLS:
        data = calculate_score(symbol)
        if data and data["score"] >= min_score:
            results.append(data)

    results.sort(key=lambda x: x["score"], reverse=True)

    return {"data": results}