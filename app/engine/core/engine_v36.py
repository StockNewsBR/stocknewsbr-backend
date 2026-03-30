# =====================================================
# STOCKNEWSBR ENGINE V36 (INSTITUTIONAL ENGINE)
# =====================================================

import numpy as np
import logging

try:
    from numba import njit
except Exception:  # pragma: no cover - optional dependency fallback
    def njit(*_args, **_kwargs):
        def decorator(fn):
            return fn

        return decorator

from app.market.warm_data_pool import get_market_pool

logger = logging.getLogger("stocknewsbr.engine.v36")

EPS = 1e-9


# =====================================================
# NUMBA CORE COMPUTE
# =====================================================

@njit(cache=True, fastmath=True)
def compute_core(price_matrix, volume_matrix):

    n_assets, n_time = price_matrix.shape

    momentum = np.zeros(n_assets, dtype=np.float32)
    trend = np.zeros(n_assets, dtype=np.float32)
    volatility = np.zeros(n_assets, dtype=np.float32)

    smart_money = np.zeros(n_assets, dtype=np.bool_)
    breakout = np.zeros(n_assets, dtype=np.bool_)

    scores = np.zeros(n_assets, dtype=np.float32)

    for i in range(n_assets):

        sum20 = 0.0
        sum5 = 0.0

        var = 0.0

        base_idx = n_time - 21

        for k in range(20):

            j = base_idx + k

            base = price_matrix[i, j]

            if base <= 0:
                base = EPS

            r = (price_matrix[i, j+1] - base) / base

            sum20 += r

            if k >= 15:
                sum5 += r

        m5 = sum5 / 5.0
        m20 = sum20 / 20.0

        momentum[i] = m5
        trend[i] = m20

        for k in range(20):

            j = base_idx + k

            base = price_matrix[i, j]

            if base <= 0:
                base = EPS

            r = (price_matrix[i, j+1] - base) / base

            diff = r - m20

            var += diff * diff

        volatility[i] = np.sqrt(var / 20.0)

        # volume logic

        vol_last = volume_matrix[i, n_time-1]

        vol_mean = 0.0

        for j in range(n_time-30, n_time):
            vol_mean += volume_matrix[i, j]

        vol_mean /= 30.0

        if vol_last > vol_mean * 2.0:
            smart_money[i] = True

        # breakout detection

        resistance = price_matrix[i, n_time-20]

        for j in range(n_time-20, n_time-1):

            p = price_matrix[i, j]

            if p > resistance:
                resistance = p

        if price_matrix[i, n_time-1] > resistance:
            breakout[i] = True

        score = m5 * 150 + m20 * 60

        if smart_money[i]:
            score += 30

        if breakout[i]:
            score += 25

        scores[i] = score

    return momentum, trend, volatility, smart_money, breakout, scores


# =====================================================
# MATRIX BUILDER
# =====================================================

def build_matrices(pool):

    tickers = []
    prices = []
    volumes = []
    min_len = None

    for ticker, df in pool.items():

        try:

            close = df.Close.values[-200:]
            volume = df.Volume.values[-200:]

            if len(close) < 120:
                continue

            tickers.append(ticker)
            prices.append(close)
            volumes.append(volume)
            min_len = len(close) if min_len is None else min(min_len, len(close))

        except Exception:
            continue

    if not prices or min_len is None:
        return [], None, None

    aligned_prices = [row[-min_len:] for row in prices]
    aligned_volumes = [row[-min_len:] for row in volumes]

    price_matrix = np.asarray(aligned_prices, dtype=np.float32, order="C")
    volume_matrix = np.asarray(aligned_volumes, dtype=np.float32, order="C")

    return tickers, price_matrix, volume_matrix


# =====================================================
# ENGINE RUNNER
# =====================================================

def run_engine():

    try:

        pool = get_market_pool()

        if not pool:
            return []

        tickers, price_matrix, volume_matrix = build_matrices(pool)

        if price_matrix is None:
            return []

        momentum, trend, volatility, smart_money, breakout, scores = compute_core(
            price_matrix,
            volume_matrix
        )

        idx = np.where(scores > 15)[0]

        if idx.size == 0:
            return []

        sorted_idx = idx[np.argsort(scores[idx])[::-1]]

        top_idx = sorted_idx[:200]

        results = []

        for i in top_idx:

            results.append({

                "ticker": tickers[i],
                "score": float(scores[i]),
                "momentum": float(momentum[i]),
                "trend": float(trend[i]),
                "volatility": float(volatility[i]),
                "smart_money": bool(smart_money[i]),
                "breakout": bool(breakout[i])

            })

        return results

    except Exception as e:

        logger.exception("Engine V36 failure: %s", e)

        return []
