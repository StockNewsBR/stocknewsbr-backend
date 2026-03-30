# =====================================================
# SYSTEM STATUS ROUTES
# =====================================================

from fastapi import APIRouter, Depends

from app.cache.signal_cache import get_signal_info
from app.cache.snapshot_cache import get_snapshot_info
from app.dependencies import require_internal_token
from app.services.media_service import get_media_status
from app.services.push_service import get_push_status
from app.services.storage_service import get_storage_status
from app.social.moderation import get_moderation_summary
from app.system.ai_worker import get_ai_worker_history, get_ai_worker_report
from app.system.observability_engine import get_metrics
from app.system.system_metrics import get_metrics_snapshot

router = APIRouter(
    prefix="/system",
    tags=["system"],
    dependencies=[Depends(require_internal_token)],
)


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

    return {
        "assets_scanned": status_metrics["assets_scanned"],
        "signals_ranked": status_metrics["signals_generated"],
        "signals_per_second": metrics["signals_per_sec"],
        "engine_latency": metrics["scan_time"],
        "cpu_percent": metrics["cpu_percent"],
        "memory_percent": metrics["memory_percent"],
    }


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
