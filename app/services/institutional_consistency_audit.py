from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List


ISSUE_DIRECTION_CONFLICT = "direction_conflict"
ISSUE_PRIORITY_NO_TRADE = "priority_no_trade"
ISSUE_APPROVED_OPERATIONAL_BLOCKED = "approved_operational_blocked"
ISSUE_MISSING_CONTRACTS = "missing_contracts"
ISSUE_GO_LIVE_INCONSISTENT = "go_live_inconsistent"
ISSUE_UNAUTHORIZED_PROMOTION = "unauthorized_promotion"
ISSUE_METRIC_DIVERGENCE = "metric_divergence"

REQUIRED_SIGNAL_CONTRACT_FIELDS = (
    "master_score",
    "master_direction",
    "master_status",
    "master_conviction",
    "master_confidence",
    "strategic_panel",
    "historical_confidence_score",
    "operational_status",
    "conviction_level",
    "priority_level",
    "final_decision",
)

_BULLISH_ACTIONS = {"BUY", "COVER", "LONG"}
_BEARISH_ACTIONS = {"SELL", "SHORT"}
_NO_TRADE_STATES = {"NO_TRADE", "DO_NOT_TRADE", "NAO_OPERAR", "NAO_OPERAR_AGORA"}


def _ticker(row: Dict[str, Any]) -> str:
    return str(row.get("ticker") or row.get("symbol") or "").upper().strip()


def _plain(value: Any) -> str:
    text = str(value or "").strip().upper()
    for source, target in (
        ("Ã", "A"),
        ("Á", "A"),
        ("À", "A"),
        ("Â", "A"),
        ("É", "E"),
        ("Ê", "E"),
        ("Í", "I"),
        ("Ó", "O"),
        ("Ô", "O"),
        ("Õ", "O"),
        ("Ú", "U"),
        ("Ç", "C"),
    ):
        text = text.replace(source, target)
    return " ".join(text.split())


def _master_direction(row: Dict[str, Any]) -> str:
    value = _plain(row.get("master_direction"))
    if value == "BULLISH":
        return "bullish"
    if value == "BEARISH":
        return "bearish"
    return ""


def _direction_from_action(value: Any) -> str:
    action = _plain(value)
    if action in _BULLISH_ACTIONS:
        return "bullish"
    if action in _BEARISH_ACTIONS:
        return "bearish"
    return ""


def _direction_from_text(value: Any) -> str:
    text = _plain(value)
    if not text:
        return ""
    bearish_markers = ("BEARISH", "VENDEDOR", "VENDA", "SHORT", "BAIXA", "BAIXISTA")
    bullish_markers = ("BULLISH", "COMPRADOR", "COMPRA", "BUY", "LONG", "ALTA", "ALTISTA")
    if any(marker in text for marker in bearish_markers):
        return "bearish"
    if any(marker in text for marker in bullish_markers):
        return "bullish"
    return ""


def _final_direction(row: Dict[str, Any]) -> str:
    for key in ("final_decision_direction", "final_direction", "final_trade_direction"):
        direction = _direction_from_text(row.get(key))
        if direction:
            return direction

    for key in ("final_trade_action", "trade_action", "signal", "action"):
        direction = _direction_from_action(row.get(key))
        if direction:
            return direction

    text_direction = _direction_from_text(
        " ".join(
            str(row.get(key) or "")
            for key in ("final_decision", "final_decision_summary", "final_decision_reason")
        )
    )
    return text_direction


def _is_critical_priority(row: Dict[str, Any]) -> bool:
    return "CRITIC" in _plain(row.get("priority_level")) or _plain(row.get("priority")) == "CRITICAL"


def _is_no_trade(row: Dict[str, Any]) -> bool:
    decision = _plain(row.get("final_decision"))
    decision_state = _plain(row.get("decision_state"))
    action = _plain(row.get("trade_action") or row.get("signal") or row.get("action"))
    if "NAO OPERAR AGORA" in decision or "NO TRADE" in decision:
        return True
    if decision_state in _NO_TRADE_STATES or action in _NO_TRADE_STATES:
        return True
    return bool(row.get("final_decision_blocks"))


def _is_blocked_operationally(row: Dict[str, Any]) -> bool:
    return (
        _plain(row.get("audit_status")) == "BLOCKED"
        or _plain(row.get("operational_status")) == "BLOCKED"
        or _is_no_trade(row)
        or row.get("radar_no_trade_now") is True
        or row.get("decision_ready") is not True
    )


def _missing_contract_fields(row: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    for field in REQUIRED_SIGNAL_CONTRACT_FIELDS:
        value = row.get(field)
        if value in (None, ""):
            missing.append(field)
        elif isinstance(value, (list, dict)) and not value:
            missing.append(field)
    return missing


def _operational_block_reason(row: Dict[str, Any]) -> str:
    reason = row.get("operational_block_reason")
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    blocks = row.get("operational_blocks")
    if isinstance(blocks, str) and blocks.strip():
        return blocks.strip()
    if isinstance(blocks, (list, tuple, set)):
        joined = "; ".join(str(item).strip() for item in blocks if str(item or "").strip())
        if joined:
            return joined
    summary = row.get("operational_summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return "Auditor aprovou a consistencia dos dados, mas as regras operacionais bloquearam a execucao."


def _issue(
    row: Dict[str, Any],
    issue_type: str,
    message: str,
    *,
    master_direction: str = "",
    final_direction: str = "",
) -> Dict[str, Any]:
    return {
        "ticker": _ticker(row),
        "type": issue_type,
        "severity": "warning",
        "message": message,
        "master_direction": master_direction or row.get("master_direction"),
        "final_direction": final_direction,
        "final_decision": row.get("final_decision"),
        "priority_level": row.get("priority_level"),
        "audit_status": row.get("audit_status"),
        "operational_status": row.get("operational_status"),
    }


def _documented_operational_block(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ticker": _ticker(row),
        "type": ISSUE_APPROVED_OPERATIONAL_BLOCKED,
        "severity": "info",
        "message": "auditor approved com operational blocked e comportamento valido documentado",
        "audit_status": row.get("audit_status"),
        "operational_status": row.get("operational_status"),
        "operational_block_reason": _operational_block_reason(row),
    }


def _score_from_issues(issues: List[Dict[str, Any]], contract_coverage_pct: float) -> float:
    penalty = 0.0
    for issue in issues:
        severity = str(issue.get("severity") or "warning").lower()
        if severity == "critical":
            penalty += 20.0
        elif severity == "warning":
            penalty += 10.0
    if contract_coverage_pct < 100.0:
        penalty += min(40.0, 100.0 - contract_coverage_pct)
    return round(max(0.0, 100.0 - penalty), 2)


def audit_institutional_consistency(
    rows: Iterable[Dict[str, Any]],
    *,
    generated_at: Any | None = None,
    snapshot: Dict[str, Any] | None = None,
    expected_go_live_ready: bool | None = None,
    institutional_metrics: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    safe_rows = [row for row in rows or [] if isinstance(row, dict)]
    issues: List[Dict[str, Any]] = []
    documented_operational_blocks: List[Dict[str, Any]] = []
    missing_contract_rows: List[Dict[str, Any]] = []
    metrics = {
        "signals_checked": len(safe_rows),
        "issues": 0,
        "direction_conflicts": 0,
        "priority_no_trade": 0,
        "approved_operational_blocked": 0,
        "documented_operational_blocks": 0,
        "missing_contracts": 0,
        "contract_complete": 0,
        "contract_coverage_pct": 100.0 if safe_rows else 0.0,
        "go_live_inconsistencies": 0,
        "promotion_violations": 0,
        "metric_divergences": 0,
        "consistency_score": 100.0,
    }

    for row in safe_rows:
        missing_fields = _missing_contract_fields(row)
        if missing_fields:
            metrics["missing_contracts"] += 1
            missing_contract_rows.append(
                {
                    "ticker": _ticker(row),
                    "missing_fields": missing_fields,
                }
            )
            issue = _issue(
                row,
                ISSUE_MISSING_CONTRACTS,
                "linha sem contrato institucional completo",
            )
            issue["severity"] = "critical"
            issue["missing_fields"] = missing_fields
            issues.append(issue)
        else:
            metrics["contract_complete"] += 1

        master_direction = _master_direction(row)
        final_direction = _final_direction(row)
        if master_direction and final_direction and master_direction != final_direction:
            metrics["direction_conflicts"] += 1
            issues.append(
                _issue(
                    row,
                    ISSUE_DIRECTION_CONFLICT,
                    "master_direction diverge da direcao operacional final",
                    master_direction=master_direction,
                    final_direction=final_direction,
                )
            )

        if _is_critical_priority(row) and _is_no_trade(row):
            metrics["priority_no_trade"] += 1
            issues.append(
                _issue(
                    row,
                    ISSUE_PRIORITY_NO_TRADE,
                    "prioridade critica combinada com nao operar agora",
                    master_direction=master_direction,
                    final_direction=final_direction,
                )
            )

        if _plain(row.get("audit_status")) == "APPROVED" and _plain(row.get("operational_status")) == "BLOCKED":
            metrics["approved_operational_blocked"] += 1
            metrics["documented_operational_blocks"] += 1
            documented_operational_blocks.append(_documented_operational_block(row))

        if _is_blocked_operationally(row) and (
            row.get("ranking_eligible") is True
            or row.get("radar_promoted") is True
            or row.get("telegram_alert_ready") is True
            or row.get("push_ready") is True
        ):
            metrics["promotion_violations"] += 1
            issue = _issue(
                row,
                ISSUE_UNAUTHORIZED_PROMOTION,
                "linha bloqueada marcada para promocao operacional",
                master_direction=master_direction,
                final_direction=final_direction,
            )
            issue["severity"] = "critical"
            issues.append(issue)

    if safe_rows:
        metrics["contract_coverage_pct"] = round(metrics["contract_complete"] / max(1, len(safe_rows)) * 100, 2)

    if isinstance(snapshot, dict) and expected_go_live_ready is not None:
        reported = snapshot.get("go_live_ready")
        if isinstance(reported, bool) and reported != bool(expected_go_live_ready):
            metrics["go_live_inconsistencies"] += 1
            issues.append(
                {
                    "ticker": "",
                    "type": ISSUE_GO_LIVE_INCONSISTENT,
                    "severity": "critical",
                    "message": "snapshot.go_live_ready diverge da fonte unica de go-live",
                    "reported_go_live_ready": reported,
                    "expected_go_live_ready": bool(expected_go_live_ready),
                }
            )

    if isinstance(snapshot, dict) and isinstance(institutional_metrics, dict):
        snapshot_consistency = snapshot.get("institutional_consistency_metrics")
        metrics_consistency = institutional_metrics.get("institutional_consistency")
        if isinstance(snapshot_consistency, dict) and isinstance(metrics_consistency, dict):
            for field in ("issues", "direction_conflicts", "priority_no_trade"):
                if int(snapshot_consistency.get(field, 0) or 0) != int(metrics_consistency.get(field, 0) or 0):
                    metrics["metric_divergences"] += 1
                    issues.append(
                        {
                            "ticker": "",
                            "type": ISSUE_METRIC_DIVERGENCE,
                            "severity": "warning",
                            "message": f"metrica institucional divergente: {field}",
                            "field": field,
                            "snapshot_value": snapshot_consistency.get(field),
                            "metrics_value": metrics_consistency.get(field),
                        }
                    )

    metrics["issues"] = len(issues)
    metrics["consistency_score"] = _score_from_issues(issues, float(metrics.get("contract_coverage_pct", 0.0) or 0.0))
    has_critical = any(str(issue.get("severity") or "").lower() == "critical" for issue in issues)
    return {
        "status": "CRITICAL" if has_critical else "WARNING" if issues else "OK",
        "issue_count": len(issues),
        "issues": issues[:100],
        "documented_operational_blocks": documented_operational_blocks[:100],
        "missing_contract_rows": missing_contract_rows[:100],
        "contract_coverage": {
            "total": len(safe_rows),
            "complete": int(metrics.get("contract_complete", 0) or 0),
            "missing": int(metrics.get("missing_contracts", 0) or 0),
            "coverage_pct": float(metrics.get("contract_coverage_pct", 0.0) or 0.0),
        },
        "institutional_consistency_score": metrics["consistency_score"],
        "metrics": metrics,
        "updated_at": generated_at or time.time(),
    }
