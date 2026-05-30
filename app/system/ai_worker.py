import importlib
import json
import logging
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List

from app.ai.feature_hub import build_ai_tool_payload
from app.cache.signal_cache import get_all_signals, get_signal_info
from app.cache.snapshot_cache import get_last_good_snapshot, get_snapshot, get_snapshot_info, update_snapshot
from app.database import engine
from app.database_schema import ensure_runtime_schema
from app.engine.market_snapshot_engine import generate_market_snapshot
from app.services.ai_alert_history_service import AI_TOOL_KEYS, persist_ai_alert_history
from app.services.legal_service import get_public_bootstrap
from app.services.poll_service import generate_weekly_polls_for_top_symbols
from app.system.ai_tab_audit import run_ai_tab_audit
from app.system.system_metrics import get_metrics_snapshot, provider_call_context, record_worker_stage_duration

logger = logging.getLogger("stocknewsbr.ai_worker")

AI_WORKER_INTERVAL = max(60, int(os.getenv("AI_WORKER_INTERVAL", "900")))
AI_WORKER_REPORT_DIR = Path(os.getenv("AI_WORKER_REPORT_DIR", "runtime/ai_worker"))
AI_WORKER_HISTORY_LIMIT = max(10, int(os.getenv("AI_WORKER_HISTORY_LIMIT", "48")))
SNAPSHOT_STALE_SECONDS = max(120, int(os.getenv("AI_WORKER_SNAPSHOT_STALE_SECONDS", "900")))
IMPORT_HEALTH_TTL_SECONDS = max(60, int(os.getenv("AI_WORKER_IMPORT_HEALTH_TTL", "1800")))
SNAPSHOT_REBUILD_COOLDOWN_SECONDS = max(60, int(os.getenv("AI_WORKER_SNAPSHOT_REBUILD_COOLDOWN", "300")))

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
_import_health_cache: Dict[str, Any] = {"timestamp": 0.0, "value": {"ok": [], "failed": []}}
_snapshot_health_cache: Dict[str, Any] = {"timestamp": 0.0, "mode": "initial", "reason": "boot"}
AI_ALERT_REQUIRED_FIELDS = {
    "ticker",
    "detected_at",
    "score",
    "signal",
    "state",
    "trigger",
    "invalidation",
    "invalidacao",
    "metrics",
    "reason",
    "news_context",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp() -> str:
    return _utc_now().replace(microsecond=0).isoformat()


def _coerce_timestamp(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None

    return None


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
    now = time.time()

    with _lock:
        cached_timestamp = float(_import_health_cache.get("timestamp") or 0.0)
        cached_value = _import_health_cache.get("value") or {"ok": [], "failed": []}

        if cached_timestamp and now - cached_timestamp < IMPORT_HEALTH_TTL_SECONDS:
            return {
                "ok": list(cached_value.get("ok", [])),
                "failed": [dict(item) for item in cached_value.get("failed", [])],
            }

    healthy = []
    failed = []

    for module_path in CRITICAL_IMPORTS:
        try:
            importlib.import_module(module_path)
            healthy.append(module_path)
        except Exception as exc:
            failed.append({"module": module_path, "error": str(exc)})

    result = {
        "ok": healthy,
        "failed": failed,
    }

    with _lock:
        _import_health_cache["timestamp"] = now
        _import_health_cache["value"] = {
            "ok": list(healthy),
            "failed": [dict(item) for item in failed],
        }

    return result


def _build_snapshot_info(snapshot_payload: Dict[str, Any], fallback_info: Dict[str, Any] | None = None) -> Dict[str, Any]:
    fallback_info = fallback_info or {}
    payload_signals = snapshot_payload.get("signals") if isinstance(snapshot_payload, dict) else []
    signal_count = len(payload_signals) if isinstance(payload_signals, list) else int(fallback_info.get("signals") or 0)
    timestamp = _coerce_timestamp(snapshot_payload.get("updated_at")) if isinstance(snapshot_payload, dict) else None
    if timestamp is None and isinstance(snapshot_payload, dict):
        timestamp = _coerce_timestamp(snapshot_payload.get("generated_at"))
    if timestamp is None:
        timestamp = _coerce_timestamp(fallback_info.get("timestamp"))

    age_seconds = None
    if timestamp is not None:
        age_seconds = max(0, int(time.time() - timestamp))
    elif fallback_info.get("age_seconds") is not None:
        age_seconds = int(fallback_info.get("age_seconds"))

    return {
        "signals": signal_count,
        "timestamp": timestamp,
        "age_seconds": age_seconds,
        "has_signals": signal_count > 0,
        "is_empty": signal_count == 0,
    }


def _snapshot_self_heal(signals: List[Dict[str, Any]], snapshot_info: Dict[str, Any]) -> Dict[str, Any]:
    current_snapshot = get_snapshot()
    last_good_snapshot = get_last_good_snapshot()
    current_signal_count = int(snapshot_info.get("signals") or 0)
    current_age = snapshot_info.get("age_seconds")
    now = time.time()
    with _lock:
        last_rebuild_at = float(_snapshot_health_cache.get("timestamp") or 0.0)
        last_mode = str(_snapshot_health_cache.get("mode") or "")
        last_reason = str(_snapshot_health_cache.get("reason") or "")
    has_current_snapshot = current_signal_count > 0
    has_last_good = bool(last_good_snapshot.get("signals"))
    should_rebuild = False
    rebuild_reason = "reuse_current_snapshot"
    source = "current"
    cooldown_remaining = 0

    rebuild_on_cooldown = (
        last_rebuild_at > 0
        and last_mode == "rebuilt"
        and now - last_rebuild_at < SNAPSHOT_REBUILD_COOLDOWN_SECONDS
    )
    if rebuild_on_cooldown:
        cooldown_remaining = max(0, int(SNAPSHOT_REBUILD_COOLDOWN_SECONDS - (now - last_rebuild_at)))

    if signals and (not has_current_snapshot or current_age is None or current_age > SNAPSHOT_STALE_SECONDS):
        if rebuild_on_cooldown:
            rebuild_reason = f"rebuild_cooldown_active:{last_reason or 'recent_rebuild'}"
            if has_current_snapshot:
                source = "current"
            elif has_last_good:
                current_snapshot = dict(last_good_snapshot)
                source = "last_good"
            else:
                source = "current"
        else:
            should_rebuild = True
            rebuild_reason = "fresh_signals_available"

    elif not signals:
        if has_current_snapshot and (current_age is None or current_age <= SNAPSHOT_STALE_SECONDS):
            rebuild_reason = "signal_cache_empty_reuse_current"
        elif has_last_good:
            current_snapshot = dict(last_good_snapshot)
            source = "last_good"
            rebuild_reason = "signal_cache_empty_reuse_last_good"
        else:
            rebuild_reason = "signal_cache_empty_alert_only"

    elif has_current_snapshot and current_age is not None and current_age > SNAPSHOT_STALE_SECONDS:
        should_rebuild = True
        rebuild_reason = "current_snapshot_stale"

    if should_rebuild:
        current_snapshot = generate_market_snapshot(signals if signals else None)
        source = "rebuilt"

    resolved_info = _build_snapshot_info(current_snapshot, snapshot_info)
    if source == "last_good":
        resolved_info["timestamp"] = _coerce_timestamp(current_snapshot.get("updated_at"))
        if resolved_info["timestamp"] is not None:
            resolved_info["age_seconds"] = max(0, int(time.time() - resolved_info["timestamp"]))
        resolved_info["signals"] = len(current_snapshot.get("signals", []))
        resolved_info["has_signals"] = resolved_info["signals"] > 0
        resolved_info["is_empty"] = resolved_info["signals"] == 0

    with _lock:
        if should_rebuild:
            _snapshot_health_cache["timestamp"] = now
            _snapshot_health_cache["mode"] = source
            _snapshot_health_cache["reason"] = rebuild_reason

    return {
        "rebuilt_snapshot": should_rebuild,
        "snapshot_info": resolved_info,
        "snapshot": current_snapshot,
        "source": source,
        "reason": rebuild_reason,
        "last_good_snapshot": last_good_snapshot if has_last_good else {},
        "cooldown_remaining_seconds": cooldown_remaining,
    }


def _health_severity(import_health: Dict[str, Any], flags: List[str], audit_status: str | None) -> str:
    if import_health.get("failed"):
        return "degraded"
    if audit_status == "degraded":
        return "degraded"
    if flags or audit_status == "warning":
        return "warning"
    return "ok"


def _safe_rows(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, dict)]


def _coerce_ai_tools(value: Any) -> Dict[str, List[Dict[str, Any]]]:
    outputs = {tool: [] for tool in AI_TOOL_KEYS}
    if not isinstance(value, dict):
        return outputs
    for tool in AI_TOOL_KEYS:
        outputs[tool] = _safe_rows(value.get(tool))
    return outputs


def _ai_tool_missing_fields(ai_tools: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    missing: Dict[str, List[Dict[str, Any]]] = {}
    for tool, rows in ai_tools.items():
        for row in _safe_rows(rows):
            absent = sorted(field for field in AI_ALERT_REQUIRED_FIELDS if row.get(field) in (None, "", [], {}))
            if absent:
                missing.setdefault(tool, []).append({"ticker": row.get("ticker"), "fields": absent})
    return missing


def _ai_tool_counts(ai_tools: Dict[str, List[Dict[str, Any]]]) -> Dict[str, int]:
    return {tool: len(_safe_rows(ai_tools.get(tool))) for tool in AI_TOOL_KEYS}


def _alert_key(tool: str, row: Dict[str, Any]) -> str:
    ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper() or "UNKNOWN"
    signal = str(row.get("signal") or "").strip().upper() or "NA"
    state = str(row.get("state") or "").strip().lower() or "na"
    return "|".join([tool, ticker, signal, state])


def _preserve_history_metadata(
    current_tools: Dict[str, List[Dict[str, Any]]],
    historical_tools: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    output = {tool: [] for tool in AI_TOOL_KEYS}
    for tool in AI_TOOL_KEYS:
        historical_by_key = {
            str(row.get("_alert_key") or _alert_key(tool, row)): row
            for row in _safe_rows(historical_tools.get(tool))
        }
        for raw_row in _safe_rows(current_tools.get(tool)):
            key = _alert_key(tool, raw_row)
            historical = historical_by_key.get(key) or {}
            row = dict(raw_row)
            row["_alert_key"] = key
            row["active"] = True
            for field in ("detected_at", "updated_at", "last_seen_at"):
                if historical.get(field):
                    row[field] = historical[field]
            output[tool].append(row)
    return output


def _refresh_ai_tools_for_cycle(
    signals: List[Dict[str, Any]],
    snapshot_payload: Dict[str, Any],
) -> Dict[str, Any]:
    source = "snapshot"
    refreshed_snapshot = False
    snapshot_payload = dict(snapshot_payload or {})
    signal_rows = _safe_rows(signals)

    if signal_rows:
        generated = generate_market_snapshot(signal_rows, reuse_last_good_on_empty=True)
        if isinstance(generated, dict):
            snapshot_payload = generated
            refreshed_snapshot = True
            source = "generated_from_signal_cache"
    else:
        snapshot_rows = _safe_rows(snapshot_payload.get("signals"))
        if snapshot_rows:
            ai_tools = build_ai_tool_payload(top_signals=snapshot_rows, ranking=snapshot_rows, limit=20)
            snapshot_payload = {
                **snapshot_payload,
                "ai_tools": ai_tools,
                "ai_tools_source": "derived_from_snapshot",
                "ai_tools_generated_at": _timestamp(),
                "stale": bool(snapshot_payload.get("stale", True)),
            }
            source = "derived_from_snapshot"

    ai_tools = _coerce_ai_tools(snapshot_payload.get("ai_tools"))
    history_persisted = False
    if any(ai_tools.values()):
        historical_ai_tools = persist_ai_alert_history(ai_tools)
        ai_tools = _preserve_history_metadata(ai_tools, historical_ai_tools)
        snapshot_payload = {
            **snapshot_payload,
            "ai_tools": ai_tools,
            "ai_tools_source": source,
            "ai_tools_generated_at": _timestamp(),
        }
        update_snapshot(snapshot_payload)
        history_persisted = True

    missing_fields = _ai_tool_missing_fields(ai_tools)
    return {
        "snapshot": snapshot_payload,
        "source": source,
        "refreshed_snapshot": refreshed_snapshot,
        "history_persisted": history_persisted,
        "counts": _ai_tool_counts(ai_tools),
        "tools_ready": sum(1 for rows in ai_tools.values() if rows),
        "missing_fields": missing_fields,
        "required_fields_ok": not bool(missing_fields) and any(ai_tools.values()),
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
    snapshot_payload = self_heal.get("snapshot") or get_snapshot()
    ai_cycle_error = None
    try:
        ai_cycle = _refresh_ai_tools_for_cycle(signals, snapshot_payload)
    except Exception as exc:
        logger.exception("AI tools cycle refresh failed: %s", exc)
        ai_cycle_error = str(exc)
        ai_cycle = {
            "snapshot": snapshot_payload,
            "source": "error",
            "refreshed_snapshot": False,
            "history_persisted": False,
            "counts": {tool: 0 for tool in AI_TOOL_KEYS},
            "tools_ready": 0,
            "missing_fields": {"cycle": [{"ticker": None, "fields": sorted(AI_ALERT_REQUIRED_FIELDS)}]},
            "required_fields_ok": False,
        }
    snapshot_payload = ai_cycle.get("snapshot") or snapshot_payload
    should_generate_polls = bool(signals) or int(self_heal["snapshot_info"].get("signals") or 0) > 0
    polls = generate_weekly_polls_for_top_symbols(limit=12) if should_generate_polls else []
    bootstrap = get_public_bootstrap()
    ai_tab_audit = run_ai_tab_audit(snapshot=snapshot_payload, refresh=False)

    health_flags: List[str] = []
    alert_flags: List[str] = []
    snapshot_state = self_heal["snapshot_info"]
    if len(signals) == 0:
        health_flags.append("signals_empty")
        alert_flags.append("signals_cache_empty")

    if not signal_info.get("timestamp"):
        health_flags.append("signal_cache_missing")
        alert_flags.append("signal_cache_missing")

    if int(snapshot_state.get("signals") or 0) == 0:
        health_flags.append("snapshot_empty")
        alert_flags.append("snapshot_empty")

    if not snapshot_state.get("timestamp"):
        health_flags.append("snapshot_missing")
        alert_flags.append("snapshot_missing")

    if snapshot_state.get("age_seconds") is not None and snapshot_state.get("age_seconds") > SNAPSHOT_STALE_SECONDS:
        health_flags.append("snapshot_stale")
        alert_flags.append("snapshot_stale")

    audit_status = ai_tab_audit.get("overall_status")
    if audit_status in {"warning", "degraded"}:
        alert_flags.append(f"audit_{audit_status}")

    if import_health["failed"]:
        alert_flags.append("imports_failed")

    if not ai_cycle.get("required_fields_ok"):
        health_flags.append("ai_tools_incomplete")
        alert_flags.append("ai_tools_incomplete")
    if ai_cycle_error:
        health_flags.append("ai_tools_cycle_error")
        alert_flags.append("ai_tools_cycle_error")

    report["status"] = _health_severity(import_health, health_flags, audit_status)
    if report["status"] == "ok" and self_heal.get("source") == "last_good":
        report["status"] = "warning"

    report.update(
        {
            "metrics": metrics,
            "signals": {
                "count": len(signals),
                "cache": signal_info,
            },
            "snapshot": self_heal["snapshot_info"],
            "market_decision": snapshot_payload.get("decision", {}),
            "ai_tools": {
                "source": ai_cycle.get("source"),
                "refreshed_snapshot": ai_cycle.get("refreshed_snapshot"),
                "history_persisted": ai_cycle.get("history_persisted"),
                "tools_ready": ai_cycle.get("tools_ready"),
                "counts": ai_cycle.get("counts"),
                "required_fields_ok": ai_cycle.get("required_fields_ok"),
                "missing_fields": ai_cycle.get("missing_fields"),
                "error": ai_cycle_error,
            },
            "snapshot_health": {
                "source": self_heal.get("source"),
                "reason": self_heal.get("reason"),
                "reused_last_good": self_heal.get("source") == "last_good",
                "rebuilt_snapshot": self_heal["rebuilt_snapshot"],
                "cooldown_remaining_seconds": self_heal.get("cooldown_remaining_seconds", 0),
                "current": snapshot_state,
                "last_good": _build_snapshot_info(self_heal.get("last_good_snapshot", {}), {}) if self_heal.get("last_good_snapshot") else {},
            },
            "imports": import_health,
            "self_heal": {
                "rebuilt_snapshot": self_heal["rebuilt_snapshot"],
                "source": self_heal.get("source"),
                "reason": self_heal.get("reason"),
                "cooldown_remaining_seconds": self_heal.get("cooldown_remaining_seconds", 0),
                "weekly_polls_ready": len(polls),
            },
            "ai_tabs": {
                "overall_status": ai_tab_audit.get("overall_status"),
                "coverage": ai_tab_audit.get("coverage", {}),
                "available_tools": ai_tab_audit.get("available_tools", []),
                "benchmark": ai_tab_audit.get("benchmark", {}),
                "batch_summary": ai_tab_audit.get("batch_summary", {}),
                "release_decision": ai_tab_audit.get("release_decision", {}),
            },
            "health_flags": health_flags,
            "alerts": alert_flags,
            "decision": {
                "action": self_heal.get("reason"),
                "severity": report["status"],
                "auto_heal_enabled": bool(signals),
                "alert_only": not bool(signals) and self_heal.get("source") in {"current", "last_good"},
                "cooldown_active": int(self_heal.get("cooldown_remaining_seconds") or 0) > 0,
                "market_action": (snapshot_payload.get("decision") or {}).get("trade_action"),
            },
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

    latest_path = AI_WORKER_REPORT_DIR / "latest_report.json"
    if latest_path.exists():
        try:
            return json.loads(latest_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "worker": "ai_worker",
        "status": "idle",
        "detail": "No cycle executed yet",
    }


def get_ai_worker_history(limit: int = 10) -> List[Dict[str, Any]]:
    with _lock:
        return [dict(item) for item in _history[: max(1, limit)]]


def ai_worker_loop(stop_event: threading.Event | None = None):
    logger.info("AI worker started | interval=%ss", AI_WORKER_INTERVAL)
    effective_stop_event = stop_event or threading.Event()

    while not effective_stop_event.is_set():
        cycle_start = time.perf_counter()
        success = False
        try:
            with provider_call_context("worker"):
                run_ai_worker_cycle()
            success = True
        except Exception as exc:
            logger.exception("AI worker cycle error: %s", exc)
        finally:
            record_worker_stage_duration("ai_worker_cycle", time.perf_counter() - cycle_start, success=success)

        if effective_stop_event.wait(AI_WORKER_INTERVAL):
            break


def start_ai_worker(stop_event: threading.Event | None = None):
    try:
        ai_worker_loop(stop_event)
    except KeyboardInterrupt:
        logger.info("AI worker stopped")
