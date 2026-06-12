# =====================================================
# STOCKNEWSBR OBSERVABILITY ENGINE (V36 OPTIMIZED)
# =====================================================

import time
import logging
import threading
from collections import deque, Counter
from typing import Dict, Any, Iterable

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
_recent_events = deque(maxlen=50)

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


def record_observability_event(kind: str, message: str, severity: str = "warning", source: str | None = None, details: Dict[str, Any] | None = None) -> None:
    try:
        with _lock:
            _recent_events.appendleft(
                {
                    "kind": str(kind or "unknown"),
                    "message": str(message or "")[:240],
                    "severity": str(severity or "warning"),
                    "source": str(source or "system"),
                    "details": dict(details or {}),
                    "timestamp": time.time(),
                }
            )
    except Exception as e:  # pragma: no cover - observability should never break runtime
        logger.exception("Observability event failure: %s", e)


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


def _health_status_from_ratio(value: float, healthy_threshold: float = 0.7, degraded_threshold: float = 0.4) -> str:
    if value >= healthy_threshold:
        return "HEALTHY"
    if value >= degraded_threshold:
        return "DEGRADED"
    return "CRITICAL"


def _count_status(items: Iterable[Dict[str, Any]], key: str = "status") -> Counter:
    counter: Counter = Counter()
    for item in items:
        status = str((item or {}).get(key) or "").upper() or "UNKNOWN"
        counter[status] += 1
    return counter


def build_observability_dashboard(
    *,
    snapshot: Dict[str, Any] | None = None,
    ai_worker: Dict[str, Any] | None = None,
    ai_tabs: Dict[str, Any] | None = None,
    polls: Dict[str, Any] | None = None,
    providers: Dict[str, Any] | None = None,
    ranking: Dict[str, Any] | None = None,
    radar: Dict[str, Any] | None = None,
    telegram: Dict[str, Any] | None = None,
    system_status: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    snapshot = snapshot or {}
    ai_worker = ai_worker or {}
    ai_tabs = ai_tabs or {}
    polls = polls or {}
    providers = providers or {}
    ranking = ranking or {}
    radar = radar or {}
    telegram = telegram or {}
    system_status = system_status or {}

    provider_rows = providers.get("items") if isinstance(providers.get("items"), list) else []
    provider_status_counts = _count_status(provider_rows)
    provider_ok = provider_status_counts.get("HEALTHY", 0)
    provider_total = sum(provider_status_counts.values()) or 1
    provider_health = _health_status_from_ratio(provider_ok / provider_total, healthy_threshold=0.66, degraded_threshold=0.33)

    snapshot_health = {
        "signals_generated": snapshot.get("signals", 0),
        "invalid": snapshot.get("invalid", 0),
        "discarded": snapshot.get("discarded", 0),
        "blocked": snapshot.get("blocked", 0),
        "status": "HEALTHY"
        if int(snapshot.get("invalid", 0) or 0) == 0 and int(snapshot.get("blocked", 0) or 0) == 0
        else "DEGRADED",
    }
    auditor_counts = _count_status([{"status": ai_tabs.get("overall_status")}])
    score_counts = Counter(str(item.get("direction") or "NEUTRAL").upper() for item in (snapshot.get("master_scores") or []) if isinstance(item, dict))
    radar_counts = _count_status([{"status": radar.get("status")}])
    ranking_counts = _count_status([{"status": ranking.get("status")}])
    telegram_counts = _count_status([{"status": telegram.get("status")}])

    recent_errors = list(_recent_events)
    if not recent_errors and isinstance(system_status.get("recent_errors"), list):
        recent_errors = [item for item in system_status.get("recent_errors", []) if isinstance(item, dict)]

    error_groups = Counter(str(item.get("kind") or "unknown") for item in recent_errors)
    system_status_value = str(system_status.get("status") or "HEALTHY").upper()
    if provider_health == "CRITICAL" or snapshot_health["status"] == "DEGRADED" and int(snapshot.get("blocked", 0) or 0) > int(snapshot.get("signals", 0) or 0):
        system_status_value = "CRITICAL"
    elif provider_health == "DEGRADED" or str(ai_worker.get("status") or "").lower() == "warning":
        system_status_value = "DEGRADED"

    return {
        "system_status": system_status_value,
        "providers": {
            "status": provider_health,
            "items": provider_rows[:12],
            "counts": dict(provider_status_counts),
        },
        "snapshot_health": snapshot_health,
        "auditor_health": {
            "status": str(ai_tabs.get("overall_status") or "IDLE").upper(),
            "counts": dict(auditor_counts),
            "blocked_ratio": round(
                int((ai_tabs.get("batch_summary") or {}).get("blocked_tools", 0) or 0)
                / max(1, int((ai_tabs.get("batch_summary") or {}).get("approved_tools", 0) or 0) + int((ai_tabs.get("batch_summary") or {}).get("blocked_tools", 0) or 0)),
                4,
            ),
        },
        "score_health": {
            "distribution": dict(score_counts),
            "status": "HEALTHY" if len(score_counts) > 1 else "DEGRADED",
        },
        "radar_health": {
            "status": str(radar.get("status") or "IDLE").upper(),
            "generated": int(radar.get("generated", 0) or 0),
            "filtered": int(radar.get("filtered", 0) or 0),
            "blocked": int(radar.get("blocked", 0) or 0),
            "counts": dict(radar_counts),
        },
        "ranking_health": {
            "status": str(ranking.get("status") or "IDLE").upper(),
            "eligible": int(ranking.get("eligible", 0) or 0),
            "discarded": int(ranking.get("discarded", 0) or 0),
            "blocked": int(ranking.get("blocked", 0) or 0),
            "counts": dict(ranking_counts),
        },
        "telegram_health": {
            "status": str(telegram.get("status") or "IDLE").upper(),
            "sent": int(telegram.get("sent", 0) or 0),
            "blocked": int(telegram.get("blocked", 0) or 0),
            "discarded": int(telegram.get("discarded", 0) or 0),
            "errors": int(telegram.get("errors", 0) or 0),
            "counts": dict(telegram_counts),
        },
        "recent_errors": recent_errors[:12],
        "error_center": {
            "total": len(recent_errors),
            "groups": dict(error_groups),
        },
        "alerts": [
            {"kind": "provider", "message": "provider degradado", "severity": "warning"} if provider_health == "DEGRADED" else None,
            {"kind": "provider", "message": "provider crítico", "severity": "critical"} if provider_health == "CRITICAL" else None,
            {"kind": "radar", "message": "radar sem sinais", "severity": "warning"} if int(radar.get("generated", 0) or 0) == 0 else None,
            {"kind": "ranking", "message": "ranking vazio", "severity": "warning"} if int(ranking.get("eligible", 0) or 0) == 0 else None,
            {"kind": "telegram", "message": "telegram parado", "severity": "warning"} if int(telegram.get("sent", 0) or 0) == 0 else None,
            {"kind": "snapshot", "message": "snapshot inválido", "severity": "warning"} if snapshot_health["status"] == "DEGRADED" else None,
        ],
    }
