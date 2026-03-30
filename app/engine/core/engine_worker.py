# =====================================================
# STOCKNEWSBR ENGINE WORKER
# Ultra Safe + High Performance
# =====================================================

import time
import logging
import threading

from app.core.settings import settings
from app.engine.market_snapshot_engine import generate_market_snapshot

# metrics
from app.system.system_metrics import (
    increment_engine_cycles,
    set_scan_time
)

logger = logging.getLogger("stocknewsbr.engine_worker")

SCAN_INTERVAL = settings.SCAN_INTERVAL


class EngineWorker:

    def __init__(self):

        self._stop_event = threading.Event()
        self._thread = None

    # -------------------------------------------------

    def _loop(self):

        logger.info("🚀 Engine worker started")

        while not self._stop_event.is_set():

            start = time.time()

            try:

                generate_market_snapshot()

                # metric: engine cycle
                increment_engine_cycles()

            except Exception as e:

                logger.exception(f"Worker crash prevented: {e}")

            duration = time.time() - start

            # metric: scan time
            set_scan_time(duration)

            sleep_time = max(1, SCAN_INTERVAL - duration)

            self._stop_event.wait(sleep_time)

        logger.info("Engine worker stopped")

    # -------------------------------------------------

    def start(self):

        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="StockNewsBR-EngineWorker"
        )

        self._thread.start()

    # -------------------------------------------------

    def stop(self):

        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=5)


engine_worker = EngineWorker()