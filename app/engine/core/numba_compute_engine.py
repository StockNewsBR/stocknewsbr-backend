import numpy as np

EPS = 1e-9


def compute_returns(price_matrix):
    prices = np.asarray(price_matrix, dtype=np.float64)

    if prices.ndim != 2 or prices.shape[1] < 2:
        return np.zeros((prices.shape[0], 0), dtype=np.float64)

    return np.diff(prices, axis=1) / (prices[:, :-1] + EPS)


def compute_momentum(returns):
    values = np.asarray(returns, dtype=np.float64)

    if values.ndim != 2 or values.shape[1] == 0:
        return np.zeros(values.shape[0], dtype=np.float64)

    window = min(5, values.shape[1])
    return values[:, -window:].mean(axis=1)


def compute_volatility(returns):
    values = np.asarray(returns, dtype=np.float64)

    if values.ndim != 2 or values.shape[1] == 0:
        return np.zeros(values.shape[0], dtype=np.float64)

    window = min(20, values.shape[1])
    return values[:, -window:].std(axis=1)
