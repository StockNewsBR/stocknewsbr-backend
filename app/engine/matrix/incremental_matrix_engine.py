# =====================================================
# INCREMENTAL MATRIX ENGINE
# =====================================================

import numpy as np
import logging

logger = logging.getLogger("stocknewsbr.engine.incremental_matrix")

_state = {
    "price_matrix": None,
    "volume_matrix": None,
    "tickers": None
}


def initialize_matrix(price_matrix, volume_matrix, tickers):

    global _state

    _state["price_matrix"] = price_matrix.copy()
    _state["volume_matrix"] = volume_matrix.copy()
    _state["tickers"] = tickers


def update_last_column(new_prices, new_volumes):

    try:

        price_matrix = _state["price_matrix"]
        volume_matrix = _state["volume_matrix"]

        if price_matrix is None:
            return None

        price_matrix[:, :-1] = price_matrix[:, 1:]
        volume_matrix[:, :-1] = volume_matrix[:, 1:]

        price_matrix[:, -1] = new_prices
        volume_matrix[:, -1] = new_volumes

        return price_matrix, volume_matrix

    except Exception as e:

        logger.error(f"Incremental matrix error: {e}")

        return None