# =====================================================
# STOCKNEWSBR ENGINE SCHEDULER
# Safe restart + thread protection
# =====================================================

import logging
import threading

from app.engine.engine_worker import engine_worker

# metrics
from app.system.system_metrics import set_workers

logger = logging.getLogger("stocknewsbr.scheduler")

_scheduler_lock = threading.Lock()
_scheduler_started = False


def start_engine_scheduler():

    global _scheduler_started

    with _scheduler_lock:

        if _scheduler_started:
            logger.info("Engine scheduler already running")
            return

        try:

            engine_worker.start()

            # metric: workers running
            set_workers(1)

            _scheduler_started = True

            logger.info("Engine scheduler started")

        except Exception as e:

            logger.exception(f"Scheduler start failure: {e}")


def stop_engine_scheduler():

    global _scheduler_started

    with _scheduler_lock:

        if not _scheduler_started:
            return

        try:

            engine_worker.stop()

            # metric: workers stopped
            set_workers(0)

            _scheduler_started = False

            logger.info("Engine scheduler stopped")

        except Exception as e:

            logger.exception(f"Scheduler stop failure: {e}")