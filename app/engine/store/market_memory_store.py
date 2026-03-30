# =====================================================
# MEMORY COLUMNAR MARKET STORE (V36 OPTIMIZED)
# =====================================================

import numpy as np
import logging
import threading
from typing import Dict, List, Optional

logger = logging.getLogger("stocknewsbr.engine.memory_store")

# Thread safety
_store_lock = threading.RLock()

# Internal store
_store: Dict[str, Optional[np.ndarray]] = {
    "tickers": [],
    "price_matrix": None,
    "volume_matrix": None,
}


# -----------------------------------------------------
# INITIALIZE STORE
# -----------------------------------------------------
def initialize_store(
    tickers: List[str],
    price_matrix: np.ndarray,
    volume_matrix: np.ndarray
) -> None:
    """
    Initialize the columnar market store.

    Parameters
    ----------
    tickers : list[str]
    price_matrix : np.ndarray
    volume_matrix : np.ndarray
    """

    try:

        if price_matrix is None or volume_matrix is None:
            logger.error("Cannot initialize store with None matrices")
            return

        if price_matrix.shape != volume_matrix.shape:
            logger.error("Price and volume matrices shape mismatch")
            return

        with _store_lock:

            _store["tickers"] = list(tickers)

            # ensure contiguous arrays (faster for numpy operations)
            _store["price_matrix"] = np.ascontiguousarray(
                price_matrix, dtype=np.float64
            )

            _store["volume_matrix"] = np.ascontiguousarray(
                volume_matrix, dtype=np.float64
            )

        logger.info(
            "Market memory store initialized | assets=%s | history=%s",
            len(tickers),
            price_matrix.shape[1],
        )

    except Exception as e:
        logger.exception("Memory store initialization failed: %s", e)


# -----------------------------------------------------
# GET STORE
# -----------------------------------------------------
def get_store() -> Dict[str, Optional[np.ndarray]]:
    """
    Returns the internal store reference (zero-copy).
    """

    return _store


# -----------------------------------------------------
# GET MATRICES
# -----------------------------------------------------
def get_matrices():
    """
    Fast access to matrices (used by engine/scanners).
    """

    return _store["price_matrix"], _store["volume_matrix"]


# -----------------------------------------------------
# UPDATE LAST COLUMN
# -----------------------------------------------------
def update_last_prices(
    prices: np.ndarray,
    volumes: np.ndarray
) -> None:
    """
    Shift matrices and append new prices/volumes.

    Parameters
    ----------
    prices : np.ndarray
    volumes : np.ndarray
    """

    try:

        with _store_lock:

            price_matrix = _store.get("price_matrix")
            volume_matrix = _store.get("volume_matrix")

            if price_matrix is None or volume_matrix is None:
                logger.warning("Market store not initialized")
                return

            if prices is None or volumes is None:
                logger.warning("Received None prices/volumes")
                return

            if len(prices) != price_matrix.shape[0]:
                logger.error("Price vector size mismatch")
                return

            if len(volumes) != volume_matrix.shape[0]:
                logger.error("Volume vector size mismatch")
                return

            # shift matrices left (O(1) view operation)
            price_matrix[:, :-1] = price_matrix[:, 1:]
            volume_matrix[:, :-1] = volume_matrix[:, 1:]

            # append latest values
            price_matrix[:, -1] = prices
            volume_matrix[:, -1] = volumes

    except Exception as e:
        logger.exception("Memory store update error: %s", e)


# -----------------------------------------------------
# GET TICKER INDEX
# -----------------------------------------------------
def get_ticker_index(ticker: str) -> Optional[int]:
    """
    Fast lookup for ticker index.
    """

    try:
        tickers = _store.get("tickers")

        if ticker not in tickers:
            return None

        return tickers.index(ticker)

    except Exception:
        return None


# -----------------------------------------------------
# STORE STATUS
# -----------------------------------------------------
def store_status() -> Dict[str, int]:
    """
    Returns store metadata for monitoring.
    """

    try:

        price_matrix = _store.get("price_matrix")

        if price_matrix is None:
            return {"assets": 0, "history": 0}

        return {
            "assets": price_matrix.shape[0],
            "history": price_matrix.shape[1],
        }

    except Exception:
        return {"assets": 0, "history": 0}