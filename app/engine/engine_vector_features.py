import numpy as np


def compute_vector_features(pool):

    results = []

    for ticker, df in pool.items():

        try:

            close = df["Close"].values
            volume = df["Volume"].values

            if close.size < 30:
                continue

            returns = np.diff(close) / close[:-1]

            momentum = float(returns[-5:].mean())

            volatility = float(returns[-10:].std())

            vol_avg = float(volume[-20:].mean())

            volume_spike = bool(volume[-1] > vol_avg * 3)

            results.append({
                "ticker": ticker,
                "momentum": momentum,
                "volatility": volatility,
                "volume_spike": volume_spike,
                "price": float(close[-1])
            })

        except Exception:
            continue

    return results