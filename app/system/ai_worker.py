import importlib
import json
import logging
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List

from app.cache.signal_cache import get_all_signals, get_signal_info
from app.cache.snapshot_cache import get_snapshot_info
from app.database import engine
from app.database_schema import ensure_runtime_schema
from app.engine.market_snapshot_engine import generate_market_snapshot
from app.services.legal_service import get_public_bootstrap
from app.services.poll_service import generate_weekly_polls_for_top_symbols
from app.system.system_metrics import get_metrics_snapshot

logger = logging.getLogger("stocknewsbr.ai_worker")

AI_WORKER_INTERVAL = max(60, int(os.getenv("AI_WORKER_INTERVAL", "900")))
AI_WORKER_REPORT_DIR = Path(os.getenv("AI_WORKER_REPORT_DIR", "runtime/ai_worker"))
AI_WORKER_HISTORY_LIMIT = max(10, int(os.getenv("AI_WORKER_HISTORY_LIMIT", "48")))
SNAPSHOT_STALE_SECONDS = max(120, int(os.getenv("AI_WORKER_SNAPSHOT_STALE_SECONDS", "900")))

CRITICAL_IMPORTS = [
    "app.auth",
    "app.api.routes_public_meta",
    "app.api.market_routes",
    "app.services.ranking",
    "app.system.stream_router",
    "app.web.routes_terminal",
]

_lock = threading.RLock()
_last_report: Dict[str, Any] = {}
_history: List[Dict[str, Any]] = []


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp() -> str:
    return _utc_now().replace(microsecond=0).isoformat()


def _ensure_report_dir():
    AI_WORKER_REPORT_DIR.mkdir(parents=True, exist_ok=True)


def _write_report(report: Dict[str, Any]):
    _ensure_report_dir()
    latest_path = AI_WORKER_REPORT_DIR / "latest_report.json"
    history_name = f"report-{int(time.time())}.json"
    history_path = AI_WORKER_REPORT_DIR / history_name
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    latest_path.write_text(payload, encoding="utf-8")
    history_path.write_text(payload, encoding="utf-8")


def _record_report(report: Dict[str, Any]):
    with _lock:
        global _last_report
        _last_report = dict(report)
        _history.insert(0, dict(report))
        del _history[AI_WORKER_HISTORY_LIMIT:]


def _import_health() -> Dict[str, Any]:
    healthy = []
    failed = []

    for module_path in CRITICAL_IMPORTS:
        try:
            importlib.import_module(module_path)
            healthy.append(module_path)
        except Exception as exc:
            failed.append({"module": module_path, "error": str(exc)})

    return {
        "ok": healthy,
        "failed": failed,
    }


def _snapshot_self_heal(signals: List[Dict[str, Any]], snapshot_info: Dict[str, Any]) -> Dict[str, Any]:
    snapshot_age = snapshot_info.get("age_seconds")
    rebuilt = False

    if signals and (snapshot_age is None or snapshot_age > SNAPSHOT_STALE_SECONDS):
        generate_market_snapshot(signals)
        rebuilt = True
        snapshot_info = get_snapshot_info()

    return {
        "rebuilt_snapshot": rebuilt,
        "snapshot_info": snapshot_info,
    }


def run_ai_worker_cycle() -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "worker": "ai_worker",
        "executed_at": _timestamp(),
        "interval_seconds": AI_WORKER_INTERVAL,
        "status": "ok",
    }

    try:
        ensure_runtime_schema(engine)
        report["schema"] = {"status": "ok"}
    except Exception as exc:
        report["status"] = "degraded"
        report["schema"] = {"status": "error", "detail": str(exc)}

    signals = get_all_signals()
    signal_info = get_signal_info()
    snapshot_info = get_snapshot_info()
    metrics = get_metrics_snapshot()
    import_health = _import_health()
    self_heal = _snapshot_self_heal(signals, snapshot_info)
    polls = generate_weekly_polls_for_top_symbols(limit=12)
    bootstrap = get_public_bootstrap()

    if import_health["failed"]:
        report["status"] = "degraded"

    health_flags = []
    snapshot_state = self_heal["snapshot_info"]

    if len(signals) == 0:
        health_flags.append("signals_empty")

    if not signal_info.get("timestamp"):
        health_flags.append("signal_cache_missing")

    if int(snapshot_state.get("signals") or 0) == 0:
        health_flags.append("snapshot_empty")

    if not snapshot_state.get("timestamp"):
        health_flags.append("snapshot_missing")

    if snapshot_state.get("age_seconds") is not None and snapshot_state.get("age_seconds") > SNAPSHOT_STALE_SECONDS:
        health_flags.append("snapshot_stale")

    if health_flags:
        report["status"] = "degraded"

    report.update(
        {
            "metrics": metrics,
            "signals": {
                "count": len(signals),
                "cache": signal_info,
            },
            "snapshot": self_heal["snapshot_info"],
            "imports": import_health,
            "self_heal": {
                "rebuilt_snapshot": self_heal["rebuilt_snapshot"],
                "weekly_polls_ready": len(polls),
            },
            "health_flags": health_flags,
            "product": {
                "primary_launch_platform": bootstrap["primary_launch_platform"],
                "subscription_unlocks": bootstrap["subscription_unlocks"],
            },
        }
    )

    _write_report(report)
    _record_report(report)
    return report


def get_ai_worker_report() -> Dict[str, Any]:
    with _lock:
        if _last_report:
            return dict(_last_report)

    return {
        "worker": "ai_worker",
        "status": "idle",
        "detail": "No cycle executed yet",
    }


def get_ai_worker_history(limit: int = 10) -> List[Dict[str, Any]]:
    with _lock:
        return [dict(item) for item in _history[: max(1, limit)]]


def ai_worker_loop():
    logger.info("AI worker started | interval=%ss", AI_WORKER_INTERVAL)

    while True:
        try:
            run_ai_worker_cycle()
        except Exception as exc:
            logger.exception("AI worker cycle error: %s", exc)

        time.sleep(AI_WORKER_INTERVAL)


def start_ai_worker():
    try:
        ai_worker_loop()
    except KeyboardInterrupt:
        logger.info("AI worker stopped")
