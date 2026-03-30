# =====================================================
# GLOBAL THREAD POOL
# =====================================================

import logging
from concurrent.futures import ThreadPoolExecutor

from app.core.settings import settings

logger = logging.getLogger("stocknewsbr.thread_pool")

MAX_WORKERS = settings.THREAD_POOL_WORKERS

thread_pool = ThreadPoolExecutor(

    max_workers=MAX_WORKERS,
    thread_name_prefix="stocknewsbr"

)

logger.info(f"Thread pool started with {MAX_WORKERS} workers")


def submit_task(fn, *args, **kwargs):

    try:

        return thread_pool.submit(fn, *args, **kwargs)

    except Exception as e:

        logger.error(f"Thread submit error: {e}")

        return None


def shutdown_pool():

    try:

        thread_pool.shutdown(wait=True)

        logger.info("Thread pool shutdown")

    except Exception as e:

        logger.error(f"Thread pool shutdown error: {e}")