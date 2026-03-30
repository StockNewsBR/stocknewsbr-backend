import numpy as np

EPS = 1e-12


def compute_vector_signals(price_matrix, volume_matrix):

    returns = np.diff(price_matrix, axis=1) / (price_matrix[:, :-1] + EPS)

    momentum = returns[:, -5:].mean(axis=1)

    trend = price_matrix[:, -10:].mean(axis=1)

    volatility = returns[:, -10:].std(axis=1)

    avg_volume = volume_matrix[:, -20:].mean(axis=1)

    volume_spike = volume_matrix[:, -1] > avg_volume * 3

    return {
        "momentum": momentum,
        "trend": trend,
        "volatility": volatility,
        "volume_spike": volume_spike
    }