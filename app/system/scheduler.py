# =====================================================
# STOCKNEWSBR TASK SCHEDULER
# Fast + Crash Safe
# =====================================================

import time
import threading
import logging
from typing import Callable, List, Dict


logger = logging.getLogger("stocknewsbr.scheduler")


# =====================================================
# STATE
# =====================================================

_tasks: List[Dict] = []

_lock = threading.RLock()

_running = False


# =====================================================
# ADD TASK
# =====================================================

def add_task(func: Callable, interval: int):

    if not callable(func) or interval <= 0:
        return False

    task = {

        "func": func,

        "interval": interval,

        "next_run": time.time() + interval

    }

    with _lock:

        _tasks.append(task)

    logger.info(f"Scheduler task added: {func.__name__} every {interval}s")

    return True


# =====================================================
# SCHEDULER LOOP
# =====================================================

def _loop():

    global _running

    while _running:

        now = time.time()
        due_tasks = []

        with _lock:
            for task in _tasks:
                if now >= task["next_run"]:
                    task["next_run"] = now + task["interval"]
                    due_tasks.append(task)

        for task in due_tasks:
            try:
                task["func"]()
            except Exception as e:
                logger.error(f"Scheduler task error: {e}")

        time.sleep(1)


# =====================================================
# START SCHEDULER
# =====================================================

def start_scheduler():

    global _running

    if _running:
        return

    _running = True

    thread = threading.Thread(

        target=_loop,

        daemon=True,

        name="stocknewsbr-scheduler"

    )

    thread.start()

    logger.info("Scheduler started")


# =====================================================
# STOP SCHEDULER
# =====================================================

def stop_scheduler():

    global _running

    _running = False

    logger.info("Scheduler stopped")
