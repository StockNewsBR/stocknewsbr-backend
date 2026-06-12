from __future__ import annotations

from typing import Any

from app.cache.snapshot_cache import get_last_good_snapshot, get_snapshot
from app.services.ai_alert_history_service import (
    AI_ALERT_MAX_ROWS_PER_TOOL,
    AI_ALERT_RESET_HOUR,
    AI_ALERT_TZ,
    AI_TOOL_KEYS,
    get_ai_alert_reset_key,
)


def _safe_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _empty_tools() -> dict[str, list[dict[str, Any]]]:
    return {key: [] for key in AI_TOOL_KEYS}


def _snapshot_tools(snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    raw_tools = snapshot.get("ai_tools")
    tools = _empty_tools()
    if not isinstance(raw_tools, dict):
        return tools
    for key in AI_TOOL_KEYS:
        tools[key] = _safe_rows(raw_tools.get(key))[:AI_ALERT_MAX_ROWS_PER_TOOL]
    return tools


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 0:
        return number
    return None


def _is_operational_row(row: dict[str, Any]) -> bool:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    auditor = row.get("auditor") if isinstance(row.get("auditor"), dict) else {}
    audit_status = str(row.get("audit_status") or auditor.get("audit_status") or row.get("auditor_status") or "").upper()
    if row.get("blocked_by_auditor") is True or auditor.get("blocked_by_auditor") is True or audit_status == "BLOCKED":
        return False
    quality = str(
        row.get("data_quality")
        or row.get("dataQuality")
        or metrics.get("data_quality")
        or metrics.get("dataQuality")
        or ""
    ).lower()
    provider_status = str(row.get("provider_status") or metrics.get("provider_status") or "").lower()
    if any(term in quality for term in ("score_only", "missing", "empty", "stale", "invalid", "failed", "error")):
        return False
    if any(term in provider_status for term in ("failed", "error", "timeout", "unavailable")):
        return False
    if row.get("stale") is True or row.get("is_stale") is True or row.get("provider_error"):
        return False
    return _positive_number(row.get("price") or metrics.get("price")) is not None and _positive_number(row.get("volume") or metrics.get("volume")) is not None


def _has_operational_tools(tools: dict[str, list[dict[str, Any]]]) -> bool:
    return any(_is_operational_row(row) for rows in tools.values() for row in rows)


def build_public_ai_tools_payload(extra_symbols: list[Any] | None = None) -> dict[str, Any]:
    del extra_symbols
    snapshot = get_snapshot()
    tools = _snapshot_tools(snapshot if isinstance(snapshot, dict) else {})
    updated_at = (snapshot.get("updated_at") or snapshot.get("generated_at")) if isinstance(snapshot, dict) else None
    if _has_operational_tools(tools):
        return {
            "reset_key": get_ai_alert_reset_key(),
            "updated_at": updated_at,
            "max_rows_per_tool": AI_ALERT_MAX_ROWS_PER_TOOL,
            "reset_hour": AI_ALERT_RESET_HOUR,
            "timezone": str(AI_ALERT_TZ),
            "source": "snapshot",
            "using_fallback": False,
            "tools": tools,
        }

    last_good_snapshot = get_last_good_snapshot()
    fallback_tools = _snapshot_tools(last_good_snapshot if isinstance(last_good_snapshot, dict) else {})
    if _has_operational_tools(fallback_tools):
        return {
            "reset_key": get_ai_alert_reset_key(),
            "updated_at": (
                last_good_snapshot.get("updated_at")
                or last_good_snapshot.get("generated_at")
                or last_good_snapshot.get("last_good_timestamp")
            ) if isinstance(last_good_snapshot, dict) else updated_at,
            "max_rows_per_tool": AI_ALERT_MAX_ROWS_PER_TOOL,
            "reset_hour": AI_ALERT_RESET_HOUR,
            "timezone": str(AI_ALERT_TZ),
            "source": "last_good_snapshot",
            "using_fallback": True,
            "tools": fallback_tools,
        }

    return {
        "reset_key": get_ai_alert_reset_key(),
        "updated_at": updated_at,
        "max_rows_per_tool": AI_ALERT_MAX_ROWS_PER_TOOL,
        "reset_hour": AI_ALERT_RESET_HOUR,
        "timezone": str(AI_ALERT_TZ),
        "source": "snapshot_unavailable",
        "using_fallback": False,
        "tools": _empty_tools(),
    }
