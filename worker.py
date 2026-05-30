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
from app.system.quote_warmup import warm_quotes_once
from app.system.system_metrics import (
    increment_engine_cycles,
    provider_call_context,
    record_worker_stage_duration,
    set_assets_scanned,
    set_scan_time,
    set_signals_generated,
    set_workers,
)

logger = logging.getLogger("stocknewsbr.worker")

SCAN_INTERVAL = max(5, int(getattr(settings, "SCAN_INTERVAL", 20)))
MAX_SIGNALS = 500
CRASH_SLEEP = 5
QUOTE_PREWARM_INTERVAL = 3
QUOTE_PREWARM_TTL_SECONDS = 120
QUOTE_PREWARM_LIMIT = 120
_last_quote_prewarm = 0.0


def safe_run_engine():
    start = time.perf_counter()
    success = False

    try:
        signals = run_engine() or []
        duration = time.perf_counter() - start

        set_scan_time(duration)
        increment_engine_cycles()
        success = True

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
    finally:
        record_worker_stage_duration("engine", time.perf_counter() - start, success=success)


def _prewarm_public_quotes():
    global _last_quote_prewarm

    now = time.time()
    if now - float(_last_quote_prewarm or 0) < QUOTE_PREWARM_TTL_SECONDS:
        return

    try:
        warm_quotes_once(limit=QUOTE_PREWARM_LIMIT)
        _last_quote_prewarm = now
    except Exception:
        logger.exception("Quote prewarm error")


def worker_loop(stop_event: threading.Event):
    logger.info("Worker started | interval=%ss", SCAN_INTERVAL)
    set_workers(1)

    try:
        while not stop_event.is_set():
            cycle_start = time.perf_counter()

            try:
                with provider_call_context("worker"):
                    signals = safe_run_engine()

                    snapshot_start = time.perf_counter()
                    try:
                        generate_market_snapshot(signals, reuse_last_good_on_empty=True)
                        record_worker_stage_duration("snapshot", time.perf_counter() - snapshot_start, success=True)
                    except Exception:
                        record_worker_stage_duration("snapshot", time.perf_counter() - snapshot_start, success=False)
                        logger.exception("Snapshot update error")

                    if signals:
                        push_start = time.perf_counter()
                        try:
                            dispatch_signal_pushes(signals)
                            record_worker_stage_duration("push_dispatch", time.perf_counter() - push_start, success=True)
                        except Exception:
                            record_worker_stage_duration("push_dispatch", time.perf_counter() - push_start, success=False)
                            logger.exception("Push dispatch error")

                    if int(time.time()) % QUOTE_PREWARM_INTERVAL == 0:
                        _prewarm_public_quotes()

            except Exception:
                logger.exception("Worker failure")

                if stop_event.wait(CRASH_SLEEP):
                    break

                continue

            cycle_time = time.perf_counter() - cycle_start
            record_worker_stage_duration("cycle", cycle_time, success=True)
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
