import yfinance as yf
from app.config import SYMBOLS


def detect_sweep(df):

    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    volume = df["Volume"]

    prev_high = high.shift(1).rolling(20).max()
    prev_low = low.shift(1).rolling(20).min()

    vol_ratio = volume.iloc[-1] / volume.rolling(20).mean().iloc[-1]

    sweep_high = high.iloc[-1] > prev_high.iloc[-1] and close.iloc[-1] < prev_high.iloc[-1]

    sweep_low = low.iloc[-1] < prev_low.iloc[-1] and close.iloc[-1] > prev_low.iloc[-1]

    if sweep_high and vol_ratio > 1.5:
        return "HIGH_SWEEP"

    if sweep_low and vol_ratio > 1.5:
        return "LOW_SWEEP"

    return None


def analyze_symbol(symbol):

    df = yf.download(symbol, period="5d", interval="15m", progress=False)

    if df is None or len(df) < 50:
        return None

    sweep = detect_sweep(df)

    if not sweep:
        return None

    return {
        "symbol": symbol.replace(".SA", ""),
        "sweep": sweep
    }


def build_sweep():

    results = []

    for symbol in SYMBOLS:

        item = analyze_symbol(symbol)

        if item:
            results.append(item)

    return results