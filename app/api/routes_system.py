# =====================================================
# SYSTEM STATUS ROUTES
# =====================================================

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.cache.snapshot_cache import get_snapshot, get_snapshot_info
from app.dependencies import require_internal_token
from app.services.media_service import get_media_status
from app.services.ranking import get_ranking
from app.services.poll_service import get_poll_store_summary
from app.services.push_service import get_push_status
from app.services.go_live_status_service import build_go_live_status
from app.services.snapshot_runtime_status import evaluate_snapshot_runtime_status
from app.services.storage_service import get_storage_status
from app.social.moderation import get_moderation_summary
from app.system.ai_tab_audit import get_ai_tab_audit_history, get_ai_tab_audit_report, run_ai_tab_audit
from app.system.observability_engine import build_observability_dashboard, get_metrics, record_observability_event
from app.system.kill_switches import get_kill_switch_status
from app.system.paper_trading import get_paper_trading_status, summarize_paper_trading_status
from app.system.system_metrics import format_prometheus_metrics, get_metrics_snapshot, get_performance_metrics_snapshot
from app.telegram.telegram_alert_engine import get_telegram_health

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


def _paper_trading_observability() -> dict:
    return summarize_paper_trading_status(get_paper_trading_status())


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
    snapshot_runtime = snapshot.get("snapshot_runtime") if isinstance(snapshot.get("snapshot_runtime"), dict) else evaluate_snapshot_runtime_status(snapshot)
    snapshot_runtime_status = str(snapshot.get("snapshot_runtime_status") or snapshot_runtime.get("status") or "").upper()

    if snapshot_runtime_status == "CRITICAL":
        return "critical"
    if snapshot_runtime_status == "DEGRADED":
        return "degraded"

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
    snapshot_info = get_snapshot_info()
    snapshot_payload = get_snapshot()
    snapshot_runtime = snapshot_info.get("snapshot_runtime") if isinstance(snapshot_info.get("snapshot_runtime"), dict) else evaluate_snapshot_runtime_status(snapshot_info)
    go_live = build_go_live_status(snapshot_payload if isinstance(snapshot_payload, dict) and snapshot_payload.get("signals") else snapshot_info, institutional_metrics=metrics.get("institutional_metrics", {}))
    paper_trading = _paper_trading_observability()

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
        "institutional_metrics": metrics.get("institutional_metrics", {}),
        "institutional_auditor": metrics.get("institutional_auditor", {}),
        "master_score": metrics.get("master_score", {}),
        "historical_confidence": metrics.get("historical_confidence", {}),
        "operational_rules": metrics.get("operational_rules", {}),
        "institutional_conviction": metrics.get("institutional_conviction", {}),
        "institutional_priority": metrics.get("institutional_priority", {}),
        "institutional_radar": metrics.get("institutional_radar", {}),
        "institutional_ranking": metrics.get("institutional_ranking", {}),
        "final_decision": metrics.get("final_decision", {}),
        "telegram_alerts": metrics.get("telegram_alerts", {}),
        "worker_runtime": metrics.get("worker_runtime", {}),
        "snapshot_cache": snapshot_info,
        "snapshot_runtime_status": snapshot_runtime.get("status"),
        "snapshot_runtime": snapshot_runtime,
        "fallback_active": bool(snapshot_runtime.get("fallback_active")),
        "go_live_ready": bool(go_live.get("go_live_ready")),
        "go_live": go_live,
        "institutional_consistency_score": go_live.get("institutional_consistency_score"),
        "contract_coverage": go_live.get("contract_coverage", {}),
        "institutional_certified": bool(go_live.get("institutional_certified")),
        "certification_timestamp": go_live.get("certification_timestamp"),
        "certification_reasons": list(go_live.get("certification_reasons") or []),
        "paper_trading": paper_trading,
        "paper_trading_enabled": paper_trading.get("paper_trading_enabled"),
        "paper_trading_status": paper_trading.get("paper_trading_status"),
        "storage": get_storage_status(),
        "media": get_media_status(),
        "push": get_push_status(),
        "kill_switches": get_kill_switch_status(),
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
    snapshot_info = get_snapshot_info()
    snapshot_payload = get_snapshot()
    snapshot_runtime = snapshot_info.get("snapshot_runtime") if isinstance(snapshot_info.get("snapshot_runtime"), dict) else evaluate_snapshot_runtime_status(snapshot_info)
    storage = get_storage_status()
    media = get_media_status()
    push = get_push_status()
    go_live = build_go_live_status(snapshot_payload if isinstance(snapshot_payload, dict) and snapshot_payload.get("signals") else snapshot_info, institutional_metrics=status_metrics.get("institutional_metrics", {}))
    paper_trading = _paper_trading_observability()

    return {
        "api_ready": True,
        "storage_ready": storage["ready"],
        "cdn_ready": media["cdn_ready"],
        "push_android_ready": push["android_ready"],
        "push_apple_ready": push["apple_ready"],
        "cache_age": status_metrics["cache_age"],
        "workers": status_metrics["workers"],
        "snapshot_runtime_status": snapshot_runtime.get("status"),
        "snapshot_runtime": snapshot_runtime,
        "fallback_active": bool(snapshot_runtime.get("fallback_active")),
        "go_live_ready": bool(go_live.get("go_live_ready")),
        "go_live": go_live,
        "institutional_consistency_score": go_live.get("institutional_consistency_score"),
        "contract_coverage": go_live.get("contract_coverage", {}),
        "institutional_certified": bool(go_live.get("institutional_certified")),
        "certification_reasons": list(go_live.get("certification_reasons") or []),
        "paper_trading": paper_trading,
        "paper_trading_enabled": paper_trading.get("paper_trading_enabled"),
        "paper_trading_status": paper_trading.get("paper_trading_status"),
        "moderation": get_moderation_summary(),
    }


@router.get("/observability/report")
def observability_report():
    metrics = get_metrics()
    status_metrics = get_metrics_snapshot()
    performance_metrics = get_performance_metrics_snapshot()
    snapshot_info = get_snapshot_info()
    telegram_health = get_telegram_health()
    paper_trading = _paper_trading_observability()
    dashboard = build_observability_dashboard(
        snapshot=snapshot_info,
        ai_worker=get_ai_worker_report(),
        ai_tabs=get_ai_tab_audit_report(),
        polls=get_poll_store_summary(),
        providers={
            "items": [
                {"provider": "system", "status": "HEALTHY"},
                {"provider": "news", "status": "HEALTHY" if get_push_status().get("android_ready") else "DEGRADED"},
            ]
        },
        ranking={"status": "HEALTHY" if get_ranking() else "DEGRADED", "eligible": len(get_ranking() or []), "discarded": 0, "blocked": 0},
        radar={"status": "HEALTHY", "generated": status_metrics.get("signals_generated", 0), "filtered": 0, "blocked": 0},
        telegram=telegram_health,
        institutional_metrics=status_metrics.get("institutional_metrics", {}),
        system_status={"status": "HEALTHY"},
    )
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
        "snapshot_runtime_status": dashboard.get("snapshot_runtime_status"),
        "go_live_ready": dashboard.get("go_live_ready"),
        "paper_trading": paper_trading,
        "dashboard": dashboard,
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


@router.get("/observability/dashboard")
def observability_dashboard():
    status_metrics = get_metrics_snapshot()
    ranking_rows = get_ranking() or []
    push_status = get_push_status()
    storage_status = get_storage_status()
    telegram_health = get_telegram_health()
    paper_trading = _paper_trading_observability()
    dashboard = build_observability_dashboard(
        snapshot=get_snapshot_info(),
        ai_worker=get_ai_worker_report(),
        ai_tabs=get_ai_tab_audit_report(),
        polls=get_poll_store_summary(),
        providers={
            "items": [
                {"provider": "yahoo", "status": "DEGRADED" if status_metrics.get("cache_age") and status_metrics.get("cache_age") > 3600 else "HEALTHY"},
                {"provider": "push", "status": "HEALTHY" if push_status.get("android_ready") else "DEGRADED"},
                {"provider": "storage", "status": "HEALTHY" if storage_status.get("ready") else "DEGRADED"},
            ]
        },
        ranking={
            "status": "HEALTHY" if ranking_rows else "DEGRADED",
            "eligible": len(ranking_rows),
            "discarded": 0,
            "blocked": 0,
        },
        radar={
            "status": "HEALTHY" if status_metrics.get("signals_generated", 0) else "DEGRADED",
            "generated": status_metrics.get("signals_generated", 0),
            "filtered": 0,
            "blocked": 0,
        },
        telegram=telegram_health,
        institutional_metrics=status_metrics.get("institutional_metrics", {}),
        system_status={"status": "HEALTHY"},
    )
    if dashboard.get("system_status") == "CRITICAL":
        record_observability_event("system", "observability dashboard critical", severity="critical")
    dashboard["paper_trading"] = paper_trading
    return dashboard


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
    snapshot_payload = get_snapshot()
    polls = get_poll_store_summary()
    status = _derive_health_status(snapshot, ai_worker, ai_tabs, polls)
    snapshot_runtime = snapshot.get("snapshot_runtime") if isinstance(snapshot.get("snapshot_runtime"), dict) else evaluate_snapshot_runtime_status(snapshot)
    go_live = build_go_live_status(snapshot_payload if isinstance(snapshot_payload, dict) and snapshot_payload.get("signals") else snapshot, institutional_metrics=get_metrics_snapshot().get("institutional_metrics", {}))
    paper_trading = _paper_trading_observability()

    return {
        "status": status,
        "go_live_ready": bool(go_live.get("go_live_ready")),
        "go_live": go_live,
        "institutional_consistency_score": go_live.get("institutional_consistency_score"),
        "contract_coverage": go_live.get("contract_coverage", {}),
        "institutional_certified": bool(go_live.get("institutional_certified")),
        "certification_reasons": list(go_live.get("certification_reasons") or []),
        "paper_trading": paper_trading,
        "snapshot": {
            "signals": snapshot.get("signals", 0),
            "timestamp": snapshot.get("timestamp"),
            "age_seconds": snapshot.get("age_seconds"),
            "has_signals": snapshot.get("has_signals", False),
            "is_empty": snapshot.get("is_empty", True),
            "source": snapshot.get("source"),
            "stale": snapshot.get("stale"),
            "snapshot_runtime_status": snapshot.get("snapshot_runtime_status"),
            "snapshot_runtime": snapshot.get("snapshot_runtime"),
            "fallback_active": snapshot.get("fallback_active", False),
            "last_good_signals": snapshot.get("last_good_signals", 0),
            "last_good_timestamp": snapshot.get("last_good_timestamp"),
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
