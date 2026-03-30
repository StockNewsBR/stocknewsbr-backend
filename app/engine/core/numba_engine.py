# =====================================================
# STOCKNEWSBR NUMBA ENGINE
# =====================================================
# JIT accelerated vector engine
# Designed for ultra fast signal computation
# =====================================================

import logging
import numpy as np

from numba import njit

logger = logging.getLogger("stocknewsbr.engine.numba")


# =====================================================
# NUMBA MOMENTUM
# =====================================================

@njit(cache=True)
def compute_momentum_nb(price_matrix):

    n_assets = price_matrix.shape[0]

    momentum = np.zeros(n_assets)

    for i in range(n_assets):

        prices = price_matrix[i]

        ret = (prices[-1] - prices[-6]) / (prices[-6] + 1e-12)

        momentum[i] = ret

    return momentum


# =====================================================
# NUMBA VOLATILITY
# =====================================================

@njit(cache=True)
def compute_volatility_nb(price_matrix):

    n_assets = price_matrix.shape[0]

    vol = np.zeros(n_assets)

    for i in range(n_assets):

        prices = price_matrix[i]

        returns = np.diff(prices)

        vol[i] = np.std(returns[-10:])

    return vol


# =====================================================
# NUMBA VOLUME SPIKE
# =====================================================

@njit(cache=True)
def compute_volume_spike_nb(volume_matrix):

    n_assets = volume_matrix.shape[0]

    spikes = np.zeros(n_assets)

    for i in range(n_assets):

        vol = volume_matrix[i]

        avg = np.mean(vol[-20:])

        if vol[-1] > avg * 3:
            spikes[i] = 1
        else:
            spikes[i] = 0

    return spikes


# =====================================================
# MAIN NUMBA ENGINE
# =====================================================

def run_numba_engine(price_matrix, volume_matrix):

    try:

        momentum = compute_momentum_nb(price_matrix)

        volatility = compute_volatility_nb(price_matrix)

        volume_spike = compute_volume_spike_nb(volume_matrix)

        return momentum, volatility, volume_spike

    except Exception as e:

        logger.error(f"Numba engine failure: {e}")

        return None, None, None