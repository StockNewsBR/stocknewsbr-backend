import yfinance as yf
import pandas as pd
from app.config import SYMBOLS


def detect_compression(df):

    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    volume = df["Volume"]

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    atr = tr.rolling(14).mean()

    atr_ratio = atr.iloc[-1] / atr.rolling(50).mean().iloc[-1]

    ranges = high - low
    nr7 = ranges.iloc[-1] == ranges.rolling(7).min().iloc[-1]

    vol_ratio = volume.iloc[-1] / volume.rolling(20).mean().iloc[-1]

    near_high = close.iloc[-1] > close.rolling(20).max().iloc[-2] * 0.97

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


def analyze_symbol(symbol):

    try:

        df = yf.download(
            symbol,
            period="10d",
            interval="15m",
            progress=False,
            auto_adjust=True
        )

        if df is None or len(df) < 100:
            return None

        score = detect_compression(df)

        if score < 60:
            return None

        return {
            "symbol": symbol.replace(".SA", ""),
            "radar_score": score
        }

    except:
        return None


def build_radar():

    results = []

    for symbol in SYMBOLS:

        item = analyze_symbol(symbol)

        if item:
            results.append(item)

    results.sort(key=lambda x: x["radar_score"], reverse=True)

    return results