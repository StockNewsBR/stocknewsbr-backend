# =====================================================
# STOCKNEWSBR NUMBA COLUMNAR ENGINE
# =====================================================
# Ultra-fast vectorized engine
# JIT compiled with Numba for maximum speed
# =====================================================

import numpy as np
import logging
from numba import njit

logger = logging.getLogger("stocknewsbr.engine.numba_columnar")


# =====================================================
# CONFIG
# =====================================================

WINDOW_RETURNS = 5
WINDOW_VOL = 10
WINDOW_VOLUME = 20


# =====================================================
# NUMBA MOMENTUM
# =====================================================

@njit(cache=True)
def compute_momentum(price_matrix):

    n = price_matrix.shape[0]
    momentum = np.zeros(n)

    for i in range(n):

        prices = price_matrix[i]

        p0 = prices[-WINDOW_RETURNS-1]
        p1 = prices[-1]

        momentum[i] = (p1 - p0) / (p0 + 1e-12)

    return momentum


# =====================================================
# NUMBA VOLATILITY
# =====================================================

@njit(cache=True)
def compute_volatility(price_matrix):

    n = price_matrix.shape[0]
    vol = np.zeros(n)

    for i in range(n):

        prices = price_matrix[i]

        returns = np.diff(prices)

        vol[i] = np.std(returns[-WINDOW_VOL:])

    return vol


# =====================================================
# NUMBA VOLUME SPIKE
# =====================================================

@njit(cache=True)
def compute_volume_spike(volume_matrix):

    n = volume_matrix.shape[0]

    spikes = np.zeros(n)

    for i in range(n):

        vol = volume_matrix[i]

        avg = np.mean(vol[-WINDOW_VOLUME:])

        if vol[-1] > avg * 3:
            spikes[i] = 1
        else:
            spikes[i] = 0

    return spikes


# =====================================================
# MAIN ENGINE
# =====================================================

def run_numba_columnar_engine(price_matrix, volume_matrix):

    try:

        momentum = compute_momentum(price_matrix)

        volatility = compute_volatility(price_matrix)

        volume_spike = compute_volume_spike(volume_matrix)

        return momentum, volatility, volume_spike

    except Exception as e:

        logger.error(f"Numba columnar engine failure: {e}")

        return None, None, None