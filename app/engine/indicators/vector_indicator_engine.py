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


def _wilder_rma(values, period):
    """Wilder's smoothing (RMA), seeded the way TradingView's ta.rma does it.

    Seed = simple mean of the first `period` samples, then recursive
    alpha = 1/period. The seed is not cosmetic: letting `ewm` seed itself off
    the first sample lands 12.7 RSI points away from Wilder at the 15-candle
    contract minimum, and is still 1.8 points off at 40 candles. It only
    converges past ~150 candles, which is exactly where nobody notices.
    """
    if len(values) < period:
        return pd.Series(float("nan"), index=values.index, dtype="float64")

    seeded = values.astype("float64").copy()
    seeded.iloc[: period - 1] = float("nan")
    seeded.iloc[period - 1] = values.iloc[:period].mean()
    return seeded.ewm(alpha=1.0 / period, adjust=False).mean()


def compute_rsi(close, period=RSI_PERIOD):

    # Drop the leading NaN so the Wilder seed lands on the first `period` real
    # deltas; reindexed back to `close` at the end so callers stay aligned.
    delta = close.diff().iloc[1:]

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = _wilder_rma(gain, period)
    avg_loss = _wilder_rma(loss, period)

    rs = avg_gain / (avg_loss + 1e-12)

    rsi = 100 - (100 / (1 + rs))

    # A window with zero movement has no RS: avg_gain/(0 + 1e-12) == 0 would
    # publish a hard "RSI 0" (oversold) for a flat/frozen series. RSI is
    # undefined there, so emit NaN and let callers decide (None / neutral).
    return rsi.mask((avg_gain <= 0) & (avg_loss <= 0)).reindex(close.index)


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
