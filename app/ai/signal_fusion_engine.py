# =====================================================
# AI SIGNAL FUSION ENGINE V2
# Ultra Fast Institutional Engine
# =====================================================

import numpy as np


def _fast_trend(arr):

    n = arr.size

    x = np.arange(n)

    x_mean = x.mean()
    y_mean = arr.mean()

    num = np.sum((x - x_mean) * (arr - y_mean))
    den = np.sum((x - x_mean) ** 2)

    if den == 0:
        return 0.0

    return float(num / den)


def compute_features(df):

    try:

        close = df["Close"].values
        volume = df["Volume"].values
        open_ = df["Open"].values
        high = df["High"].values
        low = df["Low"].values

        size = close.size

        if size < 30:
            return None

        returns = np.diff(close) / close[:-1]

        momentum = float(np.mean(returns[-5:]))

        volatility = float(np.std(returns[-10:]))

        trend = _fast_trend(close)

        vol20 = volume[-20:]
        avg_vol = float(np.mean(vol20))

        last_vol = volume[-1]

        vol_spike = last_vol > avg_vol * 3

        smart_money = last_vol > avg_vol * 2 and (close[-1] - open_[-1]) > 0

        high20 = high[-20:-1]
        low20 = low[-20:-1]

        resistance = float(np.max(high20))
        support = float(np.min(low20))

        fake_breakout = high[-1] > resistance and close[-1] < resistance

        liquidity_trap = low[-1] < support and close[-1] > support

        return {

            "momentum": momentum,
            "volatility": volatility,
            "trend_strength": trend,

            "volume_spike": vol_spike,
            "smart_money": smart_money,
            "fake_breakout": fake_breakout,
            "liquidity_sweep": liquidity_trap

        }

    except Exception:

        return None