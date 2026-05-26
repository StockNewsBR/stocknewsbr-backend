from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List
from zoneinfo import ZoneInfo


AI_ALERT_HISTORY_PATH = Path("runtime/ai_alerts/history.json")
AI_ALERT_MAX_ROWS_PER_TOOL = 20
AI_ALERT_RESET_HOUR = 7
AI_ALERT_TZ = ZoneInfo("America/Sao_Paulo")

AI_TOOL_KEYS = (
    "heat_map",
    "radar",
    "breakout_probability",
    "institutional_flow",
    "smart_money",
    "accumulation",
    "volatility_squeeze",
    "liquidity_sweep",
    "liquidity_map",
    "market_regime",
    "master_score",
)

_history_lock = threading.RLock()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_from_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _coerce_iso(value: Any, fallback: datetime) -> str:
    parsed = _parse_datetime(value)
    return _iso_from_datetime(parsed or fallback)


def get_ai_alert_reset_key(now: datetime | None = None) -> str:
    current = now or _now_utc()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local = current.astimezone(AI_ALERT_TZ)
    if local.hour < AI_ALERT_RESET_HOUR:
        local = local - timedelta(days=1)
    return local.date().isoformat()


def _safe_rows(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [deepcopy(item) for item in value if isinstance(item, dict)]


def _empty_tools() -> Dict[str, List[Dict[str, Any]]]:
    return {key: [] for key in AI_TOOL_KEYS}


def _alert_identity(tool: str, row: Dict[str, Any]) -> str:
    ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
    signal = str(row.get("signal") or "").strip().upper()
    state = str(row.get("state") or "").strip().lower()
    if not ticker:
        ticker = "UNKNOWN"
    return "|".join([tool, ticker, signal or "NA", state or "na"])


def _load_store(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _save_store(path: Path, store: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(store, handle, ensure_ascii=False, indent=2, sort_keys=True)
    tmp_path.replace(path)


def _fresh_store(reset_key: str, now_iso: str) -> Dict[str, Any]:
    return {
        "reset_key": reset_key,
        "updated_at": now_iso,
        "max_rows_per_tool": AI_ALERT_MAX_ROWS_PER_TOOL,
        "reset_hour": AI_ALERT_RESET_HOUR,
        "timezone": str(AI_ALERT_TZ),
        "tools": _empty_tools(),
    }


def _sort_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def sort_key(row: Dict[str, Any]) -> str:
        return str(
            row.get("market_data_updated_at")
            or row.get("last_bar_at")
            or row.get("bar_time")
            or row.get("time")
            or row.get("timestamp")
            or row.get("last_seen_at")
            or row.get("detected_at")
            or row.get("updated_at")
            or ""
        )

    return sorted(rows, key=sort_key, reverse=True)


def persist_ai_alert_history(
    ai_outputs: Dict[str, List[Dict[str, Any]]],
    *,
    now: datetime | None = None,
    path: Path = AI_ALERT_HISTORY_PATH,
) -> Dict[str, List[Dict[str, Any]]]:
    current = now or _now_utc()
    now_iso = _iso_from_datetime(current)
    reset_key = get_ai_alert_reset_key(current)

    with _history_lock:
        store = _load_store(path)
        if store.get("reset_key") != reset_key or not isinstance(store.get("tools"), dict):
            store = _fresh_store(reset_key, now_iso)

        tools = store.setdefault("tools", _empty_tools())
        output = _empty_tools()

        for tool in AI_TOOL_KEYS:
            existing_rows = _safe_rows(tools.get(tool))
            by_key = {
                str(row.get("_alert_key") or _alert_identity(tool, row)): row
                for row in existing_rows
            }
            for existing in by_key.values():
                existing["_alert_key"] = str(existing.get("_alert_key") or _alert_identity(tool, existing))
                existing["active"] = False

            for raw_row in _safe_rows(ai_outputs.get(tool)):
                key = _alert_identity(tool, raw_row)
                detected_iso = _coerce_iso(
                    raw_row.get("market_data_updated_at")
                    or raw_row.get("last_bar_at")
                    or raw_row.get("bar_time")
                    or raw_row.get("time")
                    or raw_row.get("timestamp")
                    or raw_row.get("detected_at")
                    or raw_row.get("updated_at"),
                    current,
                )
                seen_iso = _coerce_iso(
                    raw_row.get("market_data_updated_at")
                    or raw_row.get("last_bar_at")
                    or raw_row.get("bar_time")
                    or raw_row.get("time")
                    or raw_row.get("timestamp")
                    or raw_row.get("updated_at")
                    or raw_row.get("detected_at"),
                    current,
                )

                if key in by_key:
                    preserved_detected = detected_iso
                    preserved_updated = by_key[key].get("updated_at") or preserved_detected
                    merged = {**by_key[key], **raw_row}
                    merged["_alert_key"] = key
                    merged["detected_at"] = preserved_detected
                    merged["updated_at"] = preserved_updated
                    merged["last_seen_at"] = seen_iso
                    merged["active"] = True
                    by_key[key] = merged
                else:
                    new_row = dict(raw_row)
                    new_row["_alert_key"] = key
                    new_row["detected_at"] = detected_iso
                    new_row["updated_at"] = detected_iso
                    new_row["last_seen_at"] = seen_iso
                    new_row["active"] = True
                    by_key[key] = new_row

            rows = _sort_rows(by_key.values())[:AI_ALERT_MAX_ROWS_PER_TOOL]
            tools[tool] = rows
            output[tool] = [dict(row) for row in rows]

        store["tools"] = tools
        store["updated_at"] = now_iso
        _save_store(path, store)

    return output


def get_ai_alert_history_snapshot(
    *,
    now: datetime | None = None,
    path: Path = AI_ALERT_HISTORY_PATH,
) -> Dict[str, Any]:
    current = now or _now_utc()
    reset_key = get_ai_alert_reset_key(current)

    with _history_lock:
        store = _load_store(path)

    if store.get("reset_key") != reset_key or not isinstance(store.get("tools"), dict):
        return {
            "reset_key": reset_key,
            "max_rows_per_tool": AI_ALERT_MAX_ROWS_PER_TOOL,
            "reset_hour": AI_ALERT_RESET_HOUR,
            "timezone": str(AI_ALERT_TZ),
            "tools": _empty_tools(),
        }

    tools = _empty_tools()
    stored_tools = store.get("tools") or {}
    for tool in AI_TOOL_KEYS:
        tools[tool] = _sort_rows(_safe_rows(stored_tools.get(tool)))[:AI_ALERT_MAX_ROWS_PER_TOOL]

    return {
        "reset_key": reset_key,
        "updated_at": store.get("updated_at"),
        "max_rows_per_tool": AI_ALERT_MAX_ROWS_PER_TOOL,
        "reset_hour": AI_ALERT_RESET_HOUR,
        "timezone": str(AI_ALERT_TZ),
        "tools": tools,
    }
