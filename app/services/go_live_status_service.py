from __future__ import annotations

import os
import time
from typing import Any, Dict

from app.services.institutional_consistency_audit import audit_institutional_consistency
from app.services.snapshot_runtime_status import SNAPSHOT_RUNTIME_HEALTHY, evaluate_snapshot_runtime_status


GO_LIVE_CONSISTENCY_THRESHOLD = max(
    0.0,
    min(100.0, float(os.getenv("GO_LIVE_CONSISTENCY_THRESHOLD", "95") or 95)),
)


def _safe_rows(snapshot: Dict[str, Any]) -> list[Dict[str, Any]]:
    rows = snapshot.get("signals")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def _assumed_contract_coverage(snapshot_runtime: Dict[str, Any]) -> Dict[str, Any]:
    signals = int(snapshot_runtime.get("signals", 0) or 0)
    return {
        "total": signals,
        "complete": signals,
        "missing": 0,
        "coverage_pct": 100.0 if signals > 0 else 0.0,
        "assumed_from_runtime": True,
    }


def build_go_live_status(
    snapshot: Dict[str, Any] | None,
    *,
    institutional_metrics: Dict[str, Any] | None = None,
    now: float | None = None,
) -> Dict[str, Any]:
    payload = dict(snapshot or {})
    current_time = time.time() if now is None else float(now)
    snapshot_runtime = (
        payload.get("snapshot_runtime")
        if isinstance(payload.get("snapshot_runtime"), dict)
        else evaluate_snapshot_runtime_status(payload, now=current_time)
    )
    rows = _safe_rows(payload)
    existing_consistency = payload.get("institutional_consistency") if isinstance(payload.get("institutional_consistency"), dict) else {}
    existing_metrics = existing_consistency.get("metrics") if isinstance(existing_consistency.get("metrics"), dict) else {}
    consistency_has_score = bool(
        existing_consistency.get("institutional_consistency_score") is not None
        or existing_metrics.get("consistency_score") is not None
    )
    consistency = (
        existing_consistency
        if rows and consistency_has_score
        else audit_institutional_consistency(
            rows,
            generated_at=payload.get("generated_at") or current_time,
            snapshot=payload,
            institutional_metrics=institutional_metrics,
        )
    )
    contract_coverage = (
        consistency.get("contract_coverage")
        if isinstance(consistency.get("contract_coverage"), dict)
        else _assumed_contract_coverage(snapshot_runtime)
    )
    if not rows and int(snapshot_runtime.get("signals", 0) or 0) > 0:
        contract_coverage = _assumed_contract_coverage(snapshot_runtime)

    consistency_score = float(
        consistency.get("institutional_consistency_score")
        or (consistency.get("metrics") or {}).get("consistency_score")
        or 0.0
    )
    coverage_pct = float(contract_coverage.get("coverage_pct", 0.0) or 0.0)
    critical_issues = [
        issue
        for issue in consistency.get("issues", []) or []
        if isinstance(issue, dict) and str(issue.get("severity") or "").lower() == "critical"
    ]

    reasons: list[str] = []
    if str(snapshot_runtime.get("status") or "").upper() != SNAPSHOT_RUNTIME_HEALTHY:
        reasons.append("snapshot_not_healthy")
    if int(snapshot_runtime.get("signals", 0) or 0) <= 0:
        reasons.append("signals_empty")
    if bool(snapshot_runtime.get("fallback_active")):
        reasons.append("fallback_active")
    if coverage_pct < 100.0:
        reasons.append("contracts_incomplete")
    if consistency_score < GO_LIVE_CONSISTENCY_THRESHOLD:
        reasons.append("consistency_score_below_threshold")
    if critical_issues:
        reasons.append("critical_consistency_issues")

    go_live_ready = not reasons
    certification_reasons = [] if go_live_ready else list(reasons)
    certified = bool(go_live_ready and consistency_score >= GO_LIVE_CONSISTENCY_THRESHOLD and not critical_issues)

    return {
        "go_live_ready": go_live_ready,
        "reasons": reasons,
        "snapshot_runtime_status": snapshot_runtime.get("status"),
        "snapshot_runtime": snapshot_runtime,
        "fallback_active": bool(snapshot_runtime.get("fallback_active")),
        "institutional_consistency_score": round(consistency_score, 2),
        "consistency_threshold": GO_LIVE_CONSISTENCY_THRESHOLD,
        "consistency_status": consistency.get("status"),
        "consistency_issues": consistency.get("issues", [])[:50],
        "contract_coverage": contract_coverage,
        "institutional_certified": certified,
        "certification_timestamp": current_time if certified else None,
        "certification_reasons": certification_reasons,
    }


def attach_go_live_status(
    payload: Dict[str, Any],
    *,
    institutional_metrics: Dict[str, Any] | None = None,
    now: float | None = None,
) -> Dict[str, Any]:
    output = dict(payload or {})
    status = build_go_live_status(output, institutional_metrics=institutional_metrics, now=now)
    output["go_live_ready"] = bool(status["go_live_ready"])
    output["go_live"] = status
    output["institutional_consistency_score"] = status["institutional_consistency_score"]
    output["contract_coverage"] = status["contract_coverage"]
    output["institutional_certified"] = bool(status["institutional_certified"])
    output["certification_timestamp"] = status["certification_timestamp"]
    output["certification_reasons"] = list(status["certification_reasons"])
    return output
