from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List


ISSUE_DIRECTION_CONFLICT = "direction_conflict"
ISSUE_PRIORITY_NO_TRADE = "priority_no_trade"
ISSUE_APPROVED_OPERATIONAL_BLOCKED = "approved_operational_blocked"

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


def audit_institutional_consistency(
    rows: Iterable[Dict[str, Any]],
    *,
    generated_at: Any | None = None,
) -> Dict[str, Any]:
    safe_rows = [row for row in rows or [] if isinstance(row, dict)]
    issues: List[Dict[str, Any]] = []
    metrics = {
        "signals_checked": len(safe_rows),
        "issues": 0,
        "direction_conflicts": 0,
        "priority_no_trade": 0,
        "approved_operational_blocked": 0,
    }

    for row in safe_rows:
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
            issues.append(
                _issue(
                    row,
                    ISSUE_APPROVED_OPERATIONAL_BLOCKED,
                    "auditor approved combinado com operational blocked",
                    master_direction=master_direction,
                    final_direction=final_direction,
                )
            )

    metrics["issues"] = len(issues)
    return {
        "status": "WARNING" if issues else "OK",
        "issue_count": len(issues),
        "issues": issues[:100],
        "metrics": metrics,
        "updated_at": generated_at or time.time(),
    }
