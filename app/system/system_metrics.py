# =====================================================
# STOCKNEWSBR SYSTEM METRICS
# =====================================================

import threading
import time

# =====================================================
# ENGINE METRICS
# =====================================================

engine_cycles = 0
last_scan_time = 0.0
last_signals_generated = 0
assets_scanned = 0

engine_start_time = time.time()

# =====================================================
# CACHE METRICS
# =====================================================

cache_last_update = 0.0

# =====================================================
# WORKER METRICS
# =====================================================

workers = 0
http_requests = 0
http_errors = 0
ws_connections = 0
chat_messages = 0
reports_created = 0
uploads_completed = 0
push_sends = 0

_lock = threading.RLock()


# =====================================================
# ENGINE FUNCTIONS
# =====================================================

def increment_engine_cycles():
    global engine_cycles

    with _lock:
        engine_cycles += 1


def set_scan_time(scan_time):
    global last_scan_time

    with _lock:
        last_scan_time = float(scan_time or 0.0)


def set_signals_generated(count):
    global last_signals_generated

    with _lock:
        last_signals_generated = int(count or 0)


def set_assets_scanned(count):
    global assets_scanned

    with _lock:
        assets_scanned = int(count or 0)


# =====================================================
# CACHE FUNCTIONS
# =====================================================

def update_cache_timestamp(timestamp=None):
    global cache_last_update

    with _lock:
        cache_last_update = float(timestamp or time.time())


def get_cache_age():
    with _lock:
        last_update = cache_last_update

    if last_update == 0:
        return None

    return int(time.time() - last_update)


# =====================================================
# WORKER FUNCTIONS
# =====================================================

def set_workers(count):
    global workers

    with _lock:
        workers = max(0, int(count or 0))


def increment_http_requests():
    global http_requests

    with _lock:
        http_requests += 1


def increment_http_errors():
    global http_errors

    with _lock:
        http_errors += 1


def increment_ws_connections():
    global ws_connections

    with _lock:
        ws_connections += 1


def decrement_ws_connections():
    global ws_connections

    with _lock:
        ws_connections = max(0, ws_connections - 1)


def increment_chat_messages():
    global chat_messages

    with _lock:
        chat_messages += 1


def increment_reports():
    global reports_created

    with _lock:
        reports_created += 1


def increment_uploads():
    global uploads_completed

    with _lock:
        uploads_completed += 1


def increment_push_sends():
    global push_sends

    with _lock:
        push_sends += 1


# =====================================================
# ENGINE UPTIME
# =====================================================

def get_engine_uptime():
    return int(time.time() - engine_start_time)


# =====================================================
# PERFORMANCE CALCULATIONS
# =====================================================

def get_signals_per_second():
    with _lock:
        scan_time = last_scan_time
        signal_count = last_signals_generated

    if scan_time == 0:
        return 0

    return round(signal_count / scan_time, 2)


def get_scan_frequency():
    uptime = get_engine_uptime()

    if uptime == 0:
        return 0

    with _lock:
        cycle_count = engine_cycles

    return round(cycle_count / uptime, 4)


def get_metrics_snapshot():
    with _lock:
        return {
            "engine_cycles": engine_cycles,
            "scan_time": round(last_scan_time, 4) if last_scan_time else 0,
            "signals_generated": last_signals_generated,
            "assets_scanned": assets_scanned,
            "workers": workers,
            "cache_age": get_cache_age(),
            "http_requests": http_requests,
            "http_errors": http_errors,
            "ws_connections": ws_connections,
            "chat_messages": chat_messages,
            "reports_created": reports_created,
            "uploads_completed": uploads_completed,
            "push_sends": push_sends,
        }
