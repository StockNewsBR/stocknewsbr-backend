import numpy as np
import logging
from typing import Dict

logger = logging.getLogger("stocknewsbr.engine.feature_matrix")

EPS = 1e-9


class FeatureMatrixEngine:
    """
    Centralized feature computation engine.

    Computes all scanner features once using vectorized numpy operations.
    This avoids duplicated calculations across scanners.

    Designed for:
    - High performance
    - Zero-copy usage
    - Large universes (1000+ assets)
    """

    def __init__(self):
        self.last_features: Dict[str, np.ndarray] = {}

    def compute(self, price_matrix: np.ndarray, volume_matrix: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Compute feature matrix from price and volume matrices.

        Parameters
        ----------
        price_matrix : np.ndarray
            Shape (assets, time)
        volume_matrix : np.ndarray
            Shape (assets, time)

        Returns
        -------
        Dict[str, np.ndarray]
            Feature dictionary
        """

        try:

            if price_matrix is None or volume_matrix is None:
                logger.warning("FeatureMatrixEngine received None matrices")
                return self.last_features

            if price_matrix.shape[1] < 25:
                logger.warning("Not enough history to compute features")
                return self.last_features

            price_matrix = np.asarray(price_matrix, dtype=np.float64)
            volume_matrix = np.asarray(volume_matrix, dtype=np.float64)

            returns = np.diff(price_matrix, axis=1) / (price_matrix[:, :-1] + EPS)

            # Momentum (short-term)
            momentum = returns[:, -5:].mean(axis=1)

            # Trend (mid-term)
            trend = returns[:, -20:].mean(axis=1)

            # Volatility
            volatility = returns[:, -20:].std(axis=1)

            # Average volume
            avg_volume = volume_matrix[:, -20:].mean(axis=1)

            # Volume spike
            volume_spike = volume_matrix[:, -1] > (avg_volume * 3.0)

            # Price acceleration
            accel = returns[:, -3:].mean(axis=1) - returns[:, -10:-3].mean(axis=1)

            # Liquidity pressure
            liquidity = volume_matrix[:, -1] / (avg_volume + EPS)

            features = {
                "momentum": momentum,
                "trend": trend,
                "volatility": volatility,
                "volume_spike": volume_spike,
                "price_acceleration": accel,
                "liquidity_pressure": liquidity,
            }

            self.last_features = features
            return features

        except Exception as e:
            logger.exception("FeatureMatrixEngine compute failed: %s", e)
            return self.last_features


# Global singleton (fast access across engine modules)
feature_matrix_engine = FeatureMatrixEngine()