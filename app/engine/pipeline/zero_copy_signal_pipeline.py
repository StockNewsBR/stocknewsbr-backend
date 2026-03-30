# =====================================================
# ZERO COPY SIGNAL PIPELINE
# =====================================================

import logging

logger = logging.getLogger("stocknewsbr.engine.pipeline")


def run_pipeline(store, vector_engine):

    try:

        price_matrix = store["price_matrix"]
        volume_matrix = store["volume_matrix"]

        signals = vector_engine(
            price_matrix,
            volume_matrix
        )

        return signals

    except Exception as e:

        logger.error(f"Pipeline error: {e}")

        return None