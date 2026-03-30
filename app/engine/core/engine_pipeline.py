# =====================================================
# STOCKNEWSBR ENGINE PIPELINE WRAPPER
# =====================================================
# This wrapper keeps backward compatibility with the
# old process_pool() interface while delegating the
# execution to the new institutional event pipeline.
# =====================================================

import logging

from app.engine.core.event_pipeline import run_event_pipeline

logger = logging.getLogger("stocknewsbr.engine.pipeline")


# =====================================================
# MAIN ENTRYPOINT
# =====================================================

def process_pool(pool):

    try:

        if not pool:
            return []

        return run_event_pipeline(pool)

    except Exception as e:

        logger.error(f"Engine pipeline failure: {e}")

        return []