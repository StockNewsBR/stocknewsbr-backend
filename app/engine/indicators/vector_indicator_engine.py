import pandas as pd


def compute_indicators(data):

    close = data["Close"]
    volume = data["Volume"]

    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()

    rsi = compute_rsi(close)

    volume_mean = volume.rolling(20).mean()

    return {
        "ema20": ema20,
        "ema50": ema50,
        "rsi": rsi,
        "volume_mean": volume_mean
    }


def compute_rsi(close, period=14):

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / (avg_loss + 1e-12)

    return 100 - (100 / (1 + rs))