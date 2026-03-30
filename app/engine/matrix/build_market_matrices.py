# =====================================================
# STOCKNEWSBR MARKET MATRIX BUILDER
# =====================================================

import logging
import numpy as np

logger = logging.getLogger("stocknewsbr.engine.matrix")


# =====================================================
# BUILD MATRICES
# =====================================================

def build_market_matrices(pool):

    try:

        if not pool:
            return None

        tickers = []
        closes = []
        volumes = []

        min_len = None

        # ------------------------------------------------
        # PASS 1 — DETECT MIN LENGTH
        # ------------------------------------------------

        for ticker, df in pool.items():

            try:

                close = df["Close"].values
                volume = df["Volume"].values

                if len(close) == 0:
                    continue

                if min_len is None:
                    min_len = len(close)

                min_len = min(min_len, len(close))

                tickers.append(ticker)
                closes.append(close)
                volumes.append(volume)

            except Exception:
                continue

        if not tickers:
            return None

        asset_count = len(tickers)

        # ------------------------------------------------
        # PREALLOCATE MATRICES (FAST)
        # ------------------------------------------------

        price_matrix = np.empty((asset_count, min_len), dtype=np.float32)
        volume_matrix = np.empty((asset_count, min_len), dtype=np.float32)

        # ------------------------------------------------
        # PASS 2 — FILL MATRICES
        # ------------------------------------------------

        for i in range(asset_count):

            price_matrix[i] = closes[i][-min_len:]
            volume_matrix[i] = volumes[i][-min_len:]

        return {

            "tickers": tickers,
            "price_matrix": price_matrix,
            "volume_matrix": volume_matrix

        }

    except Exception as e:

        logger.exception("Matrix build failure: %s", e)

        return None