import numpy as np

from app.engine.core.numba_compute_engine import (
    compute_returns,
    compute_momentum,
    compute_volatility
)


def compute_signals(price_matrix, volume_matrix):

    returns = compute_returns(price_matrix)

    momentum = compute_momentum(returns)

    volatility = compute_volatility(returns)

    avg_volume = volume_matrix[:, -20:].mean(axis=1)

    volume_spike = volume_matrix[:, -1] > avg_volume * 3

    return {
        "momentum": momentum,
        "volatility": volatility,
        "volume_spike": volume_spike
    }