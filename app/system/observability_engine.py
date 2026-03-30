# =====================================================
# STOCKNEWSBR OBSERVABILITY ENGINE (V36 OPTIMIZED)
# =====================================================

import time
import logging
import threading
from typing import Dict

try:
    import psutil
except Exception:  # pragma: no cover - optional dependency fallback
    psutil = None

logger = logging.getLogger("stocknewsbr.system.observability")

_start_time = time.time()

_engine_cycles = 0
_last_scan_time = 0.0
_last_signal_count = 0

_peak_signals = 0
_total_signals = 0

_lock = threading.RLock()


# =====================================================
# RECORD ENGINE CYCLE
# =====================================================

def record_cycle(scan_time: float = 0.0, signals: int = 0):

    global _engine_cycles
    global _last_scan_time
    global _last_signal_count
    global _peak_signals
    global _total_signals

    try:

        with _lock:

            _engine_cycles += 1
            _last_scan_time = scan_time
            _last_signal_count = signals

            _total_signals += signals

            if signals > _peak_signals:
                _peak_signals = signals

    except Exception as e:
        logger.exception("Observability record failure: %s", e)


# =====================================================
# ENGINE STATS
# =====================================================

def get_engine_stats():

    try:

        with _lock:

            return {
                "cycles": _engine_cycles,
                "last_scan_time": round(_last_scan_time, 6),
                "last_signal_count": _last_signal_count,
                "peak_signals": _peak_signals,
                "total_signals": _total_signals
            }

    except Exception:
        return {}


# =====================================================
# SYSTEM METRICS
# =====================================================

def get_metrics() -> Dict:

    try:

        uptime = int(time.time() - _start_time)

        cpu = psutil.cpu_percent(interval=None) if psutil else 0
        memory = psutil.virtual_memory().percent if psutil else 0

        with _lock:

            cycles = _engine_cycles
            scan_time = _last_scan_time
            signals = _last_signal_count
            peak = _peak_signals

        signals_per_sec = 0.0

        if scan_time > 0:
            signals_per_sec = signals / scan_time

        return {
            "uptime_seconds": uptime,
            "engine_cycles": cycles,
            "scan_time": round(scan_time, 6),
            "signals_last_cycle": signals,
            "signals_per_sec": round(signals_per_sec, 2),
            "peak_signals": peak,
            "cpu_percent": cpu,
            "memory_percent": memory
        }

    except Exception as e:

        logger.exception("Observability metrics error: %s", e)

        return {
            "uptime_seconds": 0,
            "engine_cycles": 0,
            "scan_time": 0,
            "signals_last_cycle": 0,
            "signals_per_sec": 0,
            "peak_signals": 0,
            "cpu_percent": 0,
            "memory_percent": 0
        }
