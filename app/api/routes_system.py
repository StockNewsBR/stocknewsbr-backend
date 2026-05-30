# =====================================================
# SYSTEM STATUS ROUTES
# =====================================================

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.cache.signal_cache import get_signal_info
from app.cache.snapshot_cache import get_snapshot_info
from app.dependencies import require_internal_token
from app.services.media_service import get_media_status
from app.services.poll_service import get_poll_store_summary
from app.services.push_service import get_push_status
from app.services.storage_service import get_storage_status
from app.social.moderation import get_moderation_summary
from app.system.ai_tab_audit import get_ai_tab_audit_history, get_ai_tab_audit_report, run_ai_tab_audit
from app.system.observability_engine import get_metrics
from app.system.system_metrics import format_prometheus_metrics, get_metrics_snapshot, get_performance_metrics_snapshot

router = APIRouter(
    prefix="/system",
    tags=["system"],
    dependencies=[Depends(require_internal_token)],
)

HEALTH_WARNING_SNAPSHOT_AGE_SECONDS = 900
HEALTH_DEGRADED_SNAPSHOT_AGE_SECONDS = 3600


def get_ai_worker_report():
    from app.system.ai_worker import get_ai_worker_report as _get_ai_worker_report

    return _get_ai_worker_report()


def get_ai_worker_history(limit: int = 10):
    from app.system.ai_worker import get_ai_worker_history as _get_ai_worker_history

    return _get_ai_worker_history(limit=limit)


def _derive_health_status(
    snapshot: dict,
    ai_worker: dict,
    ai_tabs: dict,
    polls: dict,
) -> str:
    worker_status = str(ai_worker.get("status") or "idle").lower()
    audit_status = str(ai_tabs.get("overall_status") or "idle").lower()
    snapshot_age = snapshot.get("age_seconds")
    snapshot_is_empty = bool(snapshot.get("is_empty", True))
    snapshot_has_signals = bool(snapshot.get("has_signals", False))
    snapshot_source = str((ai_worker.get("snapshot_health") or {}).get("source") or "").lower()
    current_week_polls = int(polls.get("current_week_polls") or 0)

    if worker_status == "degraded" or audit_status == "degraded":
        return "degraded"

    if snapshot_is_empty or not snapshot_has_signals or not snapshot.get("timestamp"):
        return "degraded"

    if isinstance(snapshot_age, (int, float)):
        if snapshot_age >= HEALTH_DEGRADED_SNAPSHOT_AGE_SECONDS:
            return "degraded"
        if snapshot_age >= HEALTH_WARNING_SNAPSHOT_AGE_SECONDS:
            return "warning"

    if worker_status == "warning" or audit_status == "warning":
        return "warning"

    if snapshot_source in {"last_good", "snapshot_fallback", "exception_fallback"}:
        return "warning"

    if current_week_polls <= 0:
        return "warning"

    return "ok"


@router.get("/status")
def system_status():
    metrics = get_metrics_snapshot()

    return {
        "engine_cycles": metrics["engine_cycles"],
        "scan_time": metrics["scan_time"],
        "signals_generated": metrics["signals_generated"],
        "assets_scanned": metrics["assets_scanned"],
        "cache_age": metrics["cache_age"],
        "workers": metrics["workers"],
        "http_requests": metrics["http_requests"],
        "http_errors": metrics["http_errors"],
        "ws_connections": metrics["ws_connections"],
        "chat_messages": metrics["chat_messages"],
        "reports_created": metrics["reports_created"],
        "uploads_completed": metrics["uploads_completed"],
        "push_sends": metrics["push_sends"],
        "signal_cache": get_signal_info(),
        "snapshot_cache": get_snapshot_info(),
        "storage": get_storage_status(),
        "media": get_media_status(),
        "push": get_push_status(),
        "moderation": get_moderation_summary(),
    }


@router.get("/performance")
def system_performance():
    metrics = get_metrics()
    status_metrics = get_metrics_snapshot()
    performance_metrics = get_performance_metrics_snapshot()

    return {
        "assets_scanned": status_metrics["assets_scanned"],
        "signals_ranked": status_metrics["signals_generated"],
        "signals_per_second": metrics["signals_per_sec"],
        "engine_latency": metrics["scan_time"],
        "cpu_percent": metrics["cpu_percent"],
        "memory_percent": metrics["memory_percent"],
        **performance_metrics,
    }


@router.get("/metrics", response_class=PlainTextResponse)
def system_metrics_text():
    return format_prometheus_metrics()


@router.get("/readiness")
def system_readiness():
    status_metrics = get_metrics_snapshot()
    storage = get_storage_status()
    media = get_media_status()
    push = get_push_status()

    return {
        "api_ready": True,
        "storage_ready": storage["ready"],
        "cdn_ready": media["cdn_ready"],
        "push_android_ready": push["android_ready"],
        "push_apple_ready": push["apple_ready"],
        "cache_age": status_metrics["cache_age"],
        "workers": status_metrics["workers"],
        "moderation": get_moderation_summary(),
    }


@router.get("/observability/report")
def observability_report():
    metrics = get_metrics()
    status_metrics = get_metrics_snapshot()
    performance_metrics = get_performance_metrics_snapshot()
    return {
        "uptime_seconds": metrics["uptime_seconds"],
        "engine_cycles": status_metrics["engine_cycles"],
        "signals_generated": status_metrics["signals_generated"],
        "http_requests": status_metrics["http_requests"],
        "http_errors": status_metrics["http_errors"],
        "ws_connections": status_metrics["ws_connections"],
        "chat_messages": status_metrics["chat_messages"],
        "uploads_completed": status_metrics["uploads_completed"],
        "push_sends": status_metrics["push_sends"],
        "moderation": get_moderation_summary(),
        "performance": performance_metrics,
    }


@router.get("/engine")
def engine_observability():
    metrics = get_metrics()

    return {
        "memory_percent": metrics["memory_percent"],
        "cpu_load_percent": metrics["cpu_percent"],
        "engine_uptime_seconds": metrics["uptime_seconds"],
        "engine_cycles": metrics["engine_cycles"],
        "peak_signals": metrics["peak_signals"],
    }


@router.get("/ai-worker")
def ai_worker_status():
    return get_ai_worker_report()


@router.get("/ai-worker/history")
def ai_worker_history(limit: int = 10):
    return {"items": get_ai_worker_history(limit=limit)}


@router.get("/ai-tabs/report")
def ai_tabs_report(refresh: bool = False):
    if refresh:
        return run_ai_tab_audit(refresh=True)
    return get_ai_tab_audit_report()


@router.get("/ai-tabs/history")
def ai_tabs_history(limit: int = 10):
    return {"items": get_ai_tab_audit_history(limit=limit)}


@router.get("/health")
def system_health():
    ai_worker = get_ai_worker_report()
    ai_tabs = get_ai_tab_audit_report()
    snapshot = get_snapshot_info()
    polls = get_poll_store_summary()
    status = _derive_health_status(snapshot, ai_worker, ai_tabs, polls)

    return {
        "status": status,
        "snapshot": {
            "signals": snapshot.get("signals", 0),
            "timestamp": snapshot.get("timestamp"),
            "age_seconds": snapshot.get("age_seconds"),
            "has_signals": snapshot.get("has_signals", False),
            "is_empty": snapshot.get("is_empty", True),
        },
        "worker": {
            "status": ai_worker.get("status", "idle"),
            "snapshot_source": (ai_worker.get("snapshot_health") or {}).get("source"),
            "cooldown_remaining_seconds": (ai_worker.get("snapshot_health") or {}).get("cooldown_remaining_seconds", 0),
        },
        "audit": {
            "overall_status": ai_tabs.get("overall_status", "idle"),
            "go_live": (ai_tabs.get("release_decision") or {}).get("go_live", False),
            "approved_tools": (ai_tabs.get("batch_summary") or {}).get("approved_tools", 0),
        },
        "polls": polls,
    }
