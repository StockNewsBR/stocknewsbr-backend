from fastapi import FastAPI, Query
import pandas as pd
import numpy as np
import yfinance as yf

app = FastAPI(title="StockNewsBR API")

# =====================================================
# LISTA BASE DE AÇÕES
# =====================================================

TICKERS = [
    # Ações brasileiras
    "PETR4", "VALE3", "ITUB4", "ABEV3",
    "BBAS3", "BBDC4", "WEGE3", "MGLU3",
    "SUZB3", "PRIO3",

    # BDRs (ações USA via B3)
    "AAPL34", "AMZO34", "BABA34", "BERK34",
    "M1TA34", "MELI34", "MSFT34", "NFLX34",
    "NVDC34", "PFIZ34", "PYPL34", "ROXO34"
]

# =====================================================
# FUNÇÃO BASE
# =====================================================

def get_data(symbol: str, period="5d", interval="5m"):
    df = yf.download(symbol + ".SA", period=period, interval=interval, progress=False)
    df.dropna(inplace=True)
    return df

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
# HOME
# =====================================================

@app.get("/")
def home():
    return {"status": "StockNewsBR backend running"}

# =====================================================
# RANKING CORE
# =====================================================

def calculate_score(symbol: str):
    try:
        df = get_data(symbol)

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
            "symbol": symbol + ".SA",
            "score": max(score, 0),
            "trend": trend,
            "rsi": round(float(rsi), 2),
            "breakout": ema9 > ema21
        }

    except Exception:
        return None

# =====================================================
# ENDPOINT: RANKING
# =====================================================

@app.get("/ranking")
def ranking():
    results = []

    for ticker in TICKERS:
        data = calculate_score(ticker)
        if data:
            results.append(data)

    results.sort(key=lambda x: x["score"], reverse=True)

    return {"data": results}

# =====================================================
# ENDPOINT: TOP POR SCORE
# =====================================================

@app.get("/ranking/top")
def ranking_top(min_score: int = Query(50)):
    results = []

    for ticker in TICKERS:
        data = calculate_score(ticker)
        if data and data["score"] >= min_score:
            results.append(data)

    results.sort(key=lambda x: x["score"], reverse=True)

    return {"data": results}