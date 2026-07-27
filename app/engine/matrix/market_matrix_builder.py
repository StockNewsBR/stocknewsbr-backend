# =====================================================
# MARKET MATRIX BUILDER (V36 OPTIMIZED)
# =====================================================

import numpy as np
import logging
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger("stocknewsbr.engine.matrix")


def _extract_raw_data(tickers: List[str], pool: Dict[str, Any]) -> Tuple[List[np.ndarray], List[np.ndarray], Optional[int]]:
    """Extract close and volume arrays and find the minimum size."""
    closes = []
    volumes = []
    min_size = None

    for ticker in tickers:
        df = pool.get(ticker)

        if df is None:
            continue

        if "Close" not in df or "Volume" not in df:
            logger.warning(f"{ticker} missing Close/Volume columns")
            continue

        close = df["Close"].values
        volume = df["Volume"].values

        size = len(close)

        if size == 0:
            continue

        if min_size is None or size < min_size:
            min_size = size

        closes.append(close)
        volumes.append(volume)

    return closes, volumes, min_size


def _align_arrays(closes: List[np.ndarray], volumes: List[np.ndarray], min_size: int) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """Align all arrays to the minimum size."""
    aligned_close = []
    aligned_volume = []

    for c, v in zip(closes, volumes):
        aligned_close.append(c[-min_size:])
        aligned_volume.append(v[-min_size:])

    return aligned_close, aligned_volume


def build_market_matrices(pool: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Build aligned price and volume matrices from market data pool.

    Parameters
    ----------
    pool : Dict[str, DataFrame]
        Dict of ticker -> dataframe containing Close and Volume

    Returns
    -------
    dict
        {
            "tickers": list[str],
            "price_matrix": np.ndarray,
            "volume_matrix": np.ndarray
        }
    """
    try:
        if not pool:
            return None

        tickers = list(pool.keys())

        # -------------------------------------------------
        # PASS 1 — detect minimum history
        # -------------------------------------------------
        closes, volumes, min_size = _extract_raw_data(tickers, pool)

        if min_size is None or min_size < 10:
            logger.warning("Not enough data to build matrices")
            return None

        # -------------------------------------------------
        # PASS 2 — align arrays to same length
        # -------------------------------------------------
        aligned_close, aligned_volume = _align_arrays(closes, volumes, min_size)

        # -------------------------------------------------
        # PASS 3 — build numpy matrices
        # -------------------------------------------------
        price_matrix = np.asarray(aligned_close, dtype=np.float64)
        volume_matrix = np.asarray(aligned_volume, dtype=np.float64)

        # -------------------------------------------------
        # SAFETY CHECKS
        # -------------------------------------------------
        if price_matrix.size == 0 or volume_matrix.size == 0:
            logger.warning("Matrix build resulted in empty arrays")
            return None

        return {
            "tickers": tickers,
            "price_matrix": price_matrix,
            "volume_matrix": volume_matrix,
        }

    except Exception as e:
        logger.exception("Market matrix builder failed: %s", e)
        return None
