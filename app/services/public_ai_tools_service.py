from __future__ import annotations

from typing import Any

from app.cache.snapshot_cache import get_snapshot
from app.services.ai_alert_history_service import (
    AI_ALERT_MAX_ROWS_PER_TOOL,
    AI_ALERT_RESET_HOUR,
    AI_ALERT_TZ,
    AI_TOOL_KEYS,
    get_ai_alert_history_snapshot,
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
    quality = str(
        row.get("data_quality")
        or row.get("dataQuality")
        or metrics.get("data_quality")
        or metrics.get("dataQuality")
        or ""
    ).lower()
    if "score_only" in quality or "missing" in quality or "empty" in quality:
        return False
    return _positive_number(row.get("price") or metrics.get("price")) is not None and _positive_number(row.get("volume") or metrics.get("volume")) is not None


def _has_operational_tools(tools: dict[str, list[dict[str, Any]]]) -> bool:
    return any(_is_operational_row(row) for rows in tools.values() for row in rows)


def build_public_ai_tools_payload() -> dict[str, Any]:
    snapshot = get_snapshot()
    tools = _snapshot_tools(snapshot if isinstance(snapshot, dict) else {})
    if _has_operational_tools(tools):
        return {
            "reset_key": get_ai_alert_reset_key(),
            "updated_at": snapshot.get("updated_at") or snapshot.get("generated_at"),
            "max_rows_per_tool": AI_ALERT_MAX_ROWS_PER_TOOL,
            "reset_hour": AI_ALERT_RESET_HOUR,
            "timezone": str(AI_ALERT_TZ),
            "source": "snapshot",
            "tools": tools,
        }

    payload = dict(get_ai_alert_history_snapshot())
    payload.setdefault("source", "history")
    payload.setdefault("tools", _empty_tools())
    return payload
