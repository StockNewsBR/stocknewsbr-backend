import math

import pandas as pd


RSI_PERIOD = 14


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


def compute_rsi(close, period=RSI_PERIOD):

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / (avg_loss + 1e-12)

    return 100 - (100 / (1 + rs))


def compute_latest_rsi(close, period=RSI_PERIOD):
    try:
        normalized_period = int(period)
    except (TypeError, ValueError, OverflowError):
        return None
    if normalized_period <= 0:
        return None

    try:
        numeric = pd.to_numeric(pd.Series(close), errors="coerce")
    except (TypeError, ValueError, OverflowError):
        return None
    numeric = numeric[numeric.notna()]

    def _is_finite_number(value):
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError, OverflowError):
            return False

    numeric = numeric[numeric.map(_is_finite_number)]
    if len(numeric) < normalized_period + 1:
        return None

    try:
        calculated = compute_rsi(numeric.astype(float), period=normalized_period)
    except (TypeError, ValueError, OverflowError):
        return None
    if calculated.empty:
        return None
    try:
        value = float(calculated.iloc[-1])
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(value) or value < 0 or value > 100:
        return None
    return value
