# =====================================================
# STOCKNEWSBR WORKER (V36 HARDENED)
# =====================================================

import logging
import threading
import time

from app.core.settings import settings
from app.engine.engine_orchestrator import run_engine
from app.engine.market_snapshot_engine import generate_market_snapshot
from app.system.push_dispatcher import dispatch_signal_pushes
from app.system.system_metrics import (
    increment_engine_cycles,
    set_assets_scanned,
    set_scan_time,
    set_signals_generated,
    set_workers,
)

logger = logging.getLogger("stocknewsbr.worker")

SCAN_INTERVAL = max(5, int(getattr(settings, "SCAN_INTERVAL", 20)))
MAX_SIGNALS = 500
CRASH_SLEEP = 5


def safe_run_engine():
    start = time.perf_counter()

    try:
        signals = run_engine() or []
        duration = time.perf_counter() - start

        set_scan_time(duration)
        increment_engine_cycles()

        if not signals:
            set_signals_generated(0)
            set_assets_scanned(0)
            return []

        signals = signals[:MAX_SIGNALS]

        set_signals_generated(len(signals))
        set_assets_scanned(len(signals))

        return signals

    except Exception:
        logger.exception("Engine execution error")
        set_signals_generated(0)
        set_assets_scanned(0)
        return []


def worker_loop(stop_event: threading.Event):
    logger.info("Worker started | interval=%ss", SCAN_INTERVAL)
    set_workers(1)

    try:
        while not stop_event.is_set():
            cycle_start = time.perf_counter()

            try:
                signals = safe_run_engine()

                if signals:
                    try:
                        generate_market_snapshot(signals)
                    except Exception:
                        logger.exception("Snapshot update error")

                    try:
                        dispatch_signal_pushes(signals)
                    except Exception:
                        logger.exception("Push dispatch error")

            except Exception:
                logger.exception("Worker failure")

                if stop_event.wait(CRASH_SLEEP):
                    break

                continue

            cycle_time = time.perf_counter() - cycle_start
            sleep_time = max(1, SCAN_INTERVAL - cycle_time)

            if stop_event.wait(sleep_time):
                break
    finally:
        set_workers(0)


def start_worker(stop_event: threading.Event | None = None):
    if stop_event is None:
        stop_event = threading.Event()

    try:
        worker_loop(stop_event)
    except KeyboardInterrupt:
        logger.info("Worker stopped")


if __name__ == "__main__":
    start_worker()
