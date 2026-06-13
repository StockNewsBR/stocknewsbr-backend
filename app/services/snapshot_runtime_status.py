from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict


SNAPSHOT_RUNTIME_HEALTHY = "HEALTHY"
SNAPSHOT_RUNTIME_DEGRADED = "DEGRADED"
SNAPSHOT_RUNTIME_CRITICAL = "CRITICAL"

SNAPSHOT_MIN_HEALTHY_SIGNALS = max(1, int(os.getenv("SNAPSHOT_MIN_HEALTHY_SIGNALS", "1") or 1))
SNAPSHOT_DEGRADED_AGE_SECONDS = max(60, int(os.getenv("SNAPSHOT_DEGRADED_AGE_SECONDS", "3600") or 3600))

_EMPTY_SOURCES = {"", "empty", "exception"}
_FALLBACK_SOURCES = {"last_good", "snapshot_fallback", "exception_fallback"}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "stale"}


def _coerce_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _signal_count(snapshot: Dict[str, Any]) -> int:
    signals = snapshot.get("signals")
    if isinstance(signals, list):
        return len(signals)
    try:
        return max(0, int(signals or 0))
    except (TypeError, ValueError):
        return 0


def _source(snapshot: Dict[str, Any]) -> str:
    data_status = snapshot.get("data_status") if isinstance(snapshot.get("data_status"), dict) else {}
    return str(snapshot.get("source") or snapshot.get("snapshot_source") or data_status.get("source") or "").strip().lower()


def _timestamp(snapshot: Dict[str, Any]) -> float | None:
    for key in ("timestamp", "updated_at", "generated_at"):
        parsed = _coerce_float(snapshot.get(key))
        if parsed is not None:
            return parsed
        value = snapshot.get(key)
        if isinstance(value, str) and value.strip():
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
    return None


def evaluate_snapshot_runtime_status(snapshot: Any, *, now: float | None = None) -> Dict[str, Any]:
    now = time.time() if now is None else float(now)
    if not isinstance(snapshot, dict):
        return {
            "status": SNAPSHOT_RUNTIME_CRITICAL,
            "signals": 0,
            "source": "",
            "stale": True,
            "fallback_active": False,
            "age_seconds": None,
            "reasons": ["snapshot_missing"],
        }

    signals = _signal_count(snapshot)
    source = _source(snapshot)
    stale = _coerce_bool(snapshot.get("stale") or snapshot.get("is_stale"))
    fallback_active = source in _FALLBACK_SOURCES or bool(snapshot.get("using_fallback"))
    timestamp = _timestamp(snapshot)
    age_seconds = snapshot.get("age_seconds")
    if age_seconds is None and timestamp is not None:
        age_seconds = max(0, int(now - timestamp))

    critical_reasons = []
    degraded_reasons = []

    if signals <= 0:
        critical_reasons.append("signals_empty")
    if source in _EMPTY_SOURCES:
        critical_reasons.append("source_empty" if source in {"", "empty"} else "source_exception")
    if snapshot.get("invalid") is True or snapshot.get("snapshot_invalid") is True:
        critical_reasons.append("snapshot_invalid")

    if critical_reasons:
        status = SNAPSHOT_RUNTIME_CRITICAL
        reasons = critical_reasons
    else:
        if signals < SNAPSHOT_MIN_HEALTHY_SIGNALS:
            degraded_reasons.append("signals_insufficient")
        if stale:
            degraded_reasons.append("snapshot_stale")
        if fallback_active:
            degraded_reasons.append("fallback_active")
        if timestamp is None:
            degraded_reasons.append("timestamp_missing")
        if isinstance(age_seconds, (int, float)) and age_seconds >= SNAPSHOT_DEGRADED_AGE_SECONDS:
            degraded_reasons.append("snapshot_old")
        if not source:
            degraded_reasons.append("source_missing")

        status = SNAPSHOT_RUNTIME_DEGRADED if degraded_reasons else SNAPSHOT_RUNTIME_HEALTHY
        reasons = degraded_reasons

    return {
        "status": status,
        "signals": signals,
        "source": source,
        "stale": stale,
        "fallback_active": fallback_active,
        "age_seconds": age_seconds,
        "timestamp": timestamp,
        "last_good_signals": int(snapshot.get("last_good_signals", 0) or 0),
        "last_good_timestamp": snapshot.get("last_good_timestamp"),
        "reasons": reasons,
    }


def attach_snapshot_runtime_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    output = dict(payload or {})
    runtime = evaluate_snapshot_runtime_status(output)
    output["snapshot_runtime_status"] = runtime["status"]
    output["snapshot_runtime"] = runtime
    output["fallback_active"] = bool(runtime.get("fallback_active"))
    output["go_live_ready"] = (
        runtime["status"] == SNAPSHOT_RUNTIME_HEALTHY
        and int(runtime.get("signals", 0) or 0) > 0
        and not bool(runtime.get("fallback_active"))
    )
    return output


def evaluate_go_live_ready(
    snapshot_runtime: Dict[str, Any] | str | None,
    *,
    worker_status: Any = None,
    observability_status: Any = None,
) -> Dict[str, Any]:
    if isinstance(snapshot_runtime, dict):
        snapshot_status = str(snapshot_runtime.get("status") or "").upper()
        snapshot_signals = int(snapshot_runtime.get("signals", 0) or 0)
        fallback_active = bool(snapshot_runtime.get("fallback_active"))
    else:
        snapshot_status = str(snapshot_runtime or "").upper()
        snapshot_signals = 0
        fallback_active = False

    worker_normalized = str(worker_status or "").strip().lower()
    observability_normalized = str(observability_status or "").strip().upper()
    reasons = []

    if snapshot_status != SNAPSHOT_RUNTIME_HEALTHY or snapshot_signals <= 0 or fallback_active:
        reasons.append("snapshot_not_healthy")
    if worker_normalized not in {"ok", "healthy", "running"}:
        reasons.append("worker_not_healthy")
    if observability_normalized not in {"HEALTHY", "OK"}:
        reasons.append("observability_not_healthy")

    return {
        "go_live_ready": not reasons,
        "reasons": reasons,
        "snapshot_runtime_status": snapshot_status or SNAPSHOT_RUNTIME_CRITICAL,
        "worker_status": worker_status,
        "observability_status": observability_status,
        "fallback_active": fallback_active,
    }
