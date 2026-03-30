# =====================================================
# STOCKNEWSBR COLUMNAR ENGINE (ULTRA FAST)
# =====================================================
# Vectorized market scanner
# Designed for high performance signal detection
# =====================================================

import numpy as np
import logging

logger = logging.getLogger("stocknewsbr.engine.columnar")


# =====================================================
# CONFIG
# =====================================================

MIN_BARS = 30
WINDOW_PRICE = 50
WINDOW_MOMENTUM = 5
WINDOW_VOLATILITY = 10
WINDOW_VOLUME = 20
VOLUME_SPIKE_MULTIPLIER = 3.0


# =====================================================
# SAFE ARRAY
# =====================================================

def _safe_array(values):

    try:
        return np.asarray(values, dtype=np.float64)

    except Exception:
        return None


# =====================================================
# BUILD MATRICES
# =====================================================

def build_matrices(pool):

    tickers = []
    prices = []
    volumes = []

    try:

        for ticker, df in pool.items():

            try:

                close = df["Close"].values
                volume = df["Volume"].values

                if close.size < MIN_BARS:
                    continue

                tickers.append(ticker)

                prices.append(close[-WINDOW_PRICE:])
                volumes.append(volume[-WINDOW_PRICE:])

            except Exception:
                continue

        if not prices:
            return [], None, None

        price_matrix = _safe_array(prices)
        volume_matrix = _safe_array(volumes)

        if price_matrix is None or volume_matrix is None:
            return [], None, None

        return tickers, price_matrix, volume_matrix

    except Exception as e:

        logger.error(f"Columnar matrix build error: {e}")

        return [], None, None


# =====================================================
# COMPUTE FEATURES
# =====================================================

def compute_features(price_matrix, volume_matrix):

    try:

        # returns
        returns = np.diff(price_matrix) / (price_matrix[:, :-1] + 1e-12)

        # momentum
        momentum = np.mean(returns[:, -WINDOW_MOMENTUM:], axis=1)

        # volatility
        volatility = np.std(returns[:, -WINDOW_VOLATILITY:], axis=1)

        # average volume
        avg_volume = np.mean(volume_matrix[:, -WINDOW_VOLUME:], axis=1)

        # volume spike
        volume_spike = volume_matrix[:, -1] > avg_volume * VOLUME_SPIKE_MULTIPLIER

        return momentum, volatility, volume_spike

    except Exception as e:

        logger.error(f"Columnar feature computation error: {e}")

        return None, None, None


# =====================================================
# BUILD SIGNALS
# =====================================================

def build_signals(tickers, momentum, volatility, volume_spike, price_matrix):

    signals = []

    try:

        last_prices = price_matrix[:, -1]

        for i in range(len(tickers)):

            try:

                signals.append({

                    "ticker": tickers[i],

                    "price": float(last_prices[i]),

                    "momentum": float(momentum[i]),

                    "volatility": float(volatility[i]),

                    "volume_spike": bool(volume_spike[i])

                })

            except Exception:
                continue

    except Exception as e:

        logger.error(f"Columnar signal build error: {e}")

    return signals


# =====================================================
# MAIN ENGINE
# =====================================================

def run_columnar_engine(pool):

    try:

        tickers, price_matrix, volume_matrix = build_matrices(pool)

        if price_matrix is None:
            return []

        momentum, volatility, volume_spike = compute_features(

            price_matrix,
            volume_matrix

        )

        if momentum is None:
            return []

        signals = build_signals(

            tickers,
            momentum,
            volatility,
            volume_spike,
            price_matrix

        )

        return signals

    except Exception as e:

        logger.error(f"Columnar engine failure: {e}")

        return []