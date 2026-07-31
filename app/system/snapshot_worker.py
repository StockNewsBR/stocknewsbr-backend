# =====================================================
# STOCKNEWSBR SNAPSHOT WORKER
# Ultra Fast + Crash Safe
# =====================================================

import os
import time
import logging
import threading

from app.cache.signal_cache import get_all_signals
from app.engine.market_snapshot_engine import generate_market_snapshot
from app.system.system_metrics import provider_call_context, record_worker_stage_duration


logger = logging.getLogger("stocknewsbr.snapshot_worker")


# =====================================================
# STATE
# =====================================================

_snapshot_thread = None

_stop_event = threading.Event()

_lock = threading.RLock()


# -----------------------------------------------------
# SNAPSHOT LOOP
# -----------------------------------------------------

def _snapshot_loop():

    logger.info("Snapshot worker started")

    try:

        interval = max(30, int(os.getenv("GLOBAL_SNAPSHOT_INTERVAL_SECONDS", "300")))

    except Exception:

        interval = 300

    while not _stop_event.is_set():

        start = time.time()

        success = False
        try:
            with provider_call_context("worker"):
                cached_signals = get_all_signals()

                if cached_signals:
                    generate_market_snapshot(cached_signals, reuse_last_good_on_empty=True)
                else:
                    # Preserve cold-start/self-heal behavior when the shared signal cache is empty.
                    generate_market_snapshot()
                success = True

        except Exception as e:

            logger.exception("Snapshot worker error: %s", e)

        duration = time.time() - start
        record_worker_stage_duration("snapshot_worker_cycle", duration, success=success)

        # prevent drift
        sleep_time = max(1, interval - duration)

        _stop_event.wait(sleep_time)

    logger.info("Snapshot worker stopped")


# -----------------------------------------------------
# START WORKER
# -----------------------------------------------------

def start_snapshot_worker():

    global _snapshot_thread

    with _lock:

        if _snapshot_thread and _snapshot_thread.is_alive():

            logger.info("Snapshot worker already running")

            return False

        try:

            _stop_event.clear()

            _snapshot_thread = threading.Thread(

                target=_snapshot_loop,

                daemon=True,

                name="StockNewsBR-SnapshotWorker"

            )

            _snapshot_thread.start()

            logger.info("Snapshot worker launched")

            return True

        except Exception as e:

            logger.exception("Snapshot worker start failed: %s", e)

            return False


# -----------------------------------------------------
# STOP WORKER
# -----------------------------------------------------

def stop_snapshot_worker():

    global _snapshot_thread

    try:

        _stop_event.set()

        with _lock:

            thread = _snapshot_thread

        if thread and thread.is_alive():

            thread.join(timeout=5)

        logger.info("Snapshot worker stopped")

    except Exception as e:

        logger.error("Snapshot worker stop error: %s", e)
