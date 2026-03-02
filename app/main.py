from fastapi import FastAPI, Query
import pandas as pd
import pandas_ta as ta
import yfinance as yf

app = FastAPI(title="StockNewsBR API")

# =====================================================
# LISTA BASE DE AÇÕES (pode expandir depois)
# =====================================================

TICKERS = [
    "PETR4", "VALE3", "ITUB4", "ABEV3",
    "BBAS3", "BBDC4", "WEGE3", "MGLU3",
    "SUZB3", "PRIO3"
]

# =====================================================
# FUNÇÃO BASE
# =====================================================

def get_data(symbol: str, period="5d", interval="5m"):
    df = yf.download(symbol + ".SA", period=period, interval=interval, progress=False)
    df.dropna(inplace=True)
    return df

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

        # RSI
        df["RSI"] = ta.rsi(df["Close"], length=14)
        rsi = df["RSI"].iloc[-1]

        # MACD
        macd_df = ta.macd(df["Close"])
        df = pd.concat([df, macd_df], axis=1)

        macd_col = [c for c in df.columns if "MACD_" in c and "MACDs" not in c][0]
        signal_col = [c for c in df.columns if "MACDs_" in c][0]

        macd = df[macd_col].iloc[-1]
        signal = df[signal_col].iloc[-1]

        # Tendência simples (média curta vs longa)
        ema9 = ta.ema(df["Close"], length=9).iloc[-1]
        ema21 = ta.ema(df["Close"], length=21).iloc[-1]

        score = 0

        # RSI
        if rsi < 30:
            score += 25
        elif rsi < 50:
            score += 15
        elif rsi > 70:
            score -= 10

        # MACD
        if macd > signal:
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