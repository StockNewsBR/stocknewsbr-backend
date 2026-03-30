# =====================================================
# MULTICORE ENGINE SCHEDULER
# =====================================================

import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("stocknewsbr.engine.scheduler")

MAX_WORKERS = 4


def run_parallel(tasks):

    results = []

    with ThreadPoolExecutor(MAX_WORKERS) as executor:

        futures = [executor.submit(t) for t in tasks]

        for f in futures:

            try:
                results.append(f.result())

            except Exception as e:

                logger.warning(f"Task error: {e}")

    return results