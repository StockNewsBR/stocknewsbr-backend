from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from app.ai.ai_common import describe_state
from app.cache.snapshot_cache import get_last_good_snapshot, get_snapshot
from app.services.ai_alert_history_service import (
    AI_ALERT_MAX_ROWS_PER_TOOL,
    AI_ALERT_RESET_HOUR,
    AI_ALERT_TZ,
    AI_TOOL_KEYS,
    get_ai_alert_reset_key,
)
from app.services.go_live_status_service import build_go_live_status
from app.services.snapshot_contract import (
    QUALITY_EMPTY,
    QUALITY_INVALID,
    QUALITY_SCORE_ONLY,
    QUALITY_STALE,
    coerce_data_quality,
    has_positive_value,
    is_actionable_snapshot_row,
    normalize_ai_tools_for_decision_context,
)
from app.services.symbol_registry import canonical_symbol
from app.system.kill_switches import is_ai_decisions_disabled, symbol_block_reason


logger = logging.getLogger("stocknewsbr.public_ai_tools")


def _empty_tools() -> dict[str, list[dict[str, Any]]]:
    return {key: [] for key in AI_TOOL_KEYS}


def _normalize_tool(value: Any) -> str | None:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    normalized = {"smartmoney": "smart_money", "news_ia": "news"}.get(normalized, normalized)
    return normalized if normalized in AI_TOOL_KEYS else None


def _normalize_timeframe(value: Any) -> str | None:
    normalized = str(value or "").strip().upper().replace(" ", "")
    if not normalized:
        return None
    if len(normalized) > 16 or not all(character.isalnum() or character in {"_", "-"} for character in normalized):
        return None
    return normalized


def _normalize_symbols(extra_symbols: list[Any] | None, symbol: Any) -> tuple[tuple[str, ...], str | None]:
    explicit = canonical_symbol(symbol) if str(symbol or "").strip() else ""
    normalized: list[str] = []
    for value in ([symbol] if str(symbol or "").strip() else []) + list(extra_symbols or []):
        resolved = canonical_symbol(value)
        if resolved and resolved not in normalized:
            normalized.append(resolved)
    primary = explicit or (normalized[0] if len(normalized) == 1 else None)
    return tuple(normalized), primary or None


def _row_timeframe(row: dict[str, Any]) -> str | None:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    values = (
        row.get("timeframe"), row.get("analysis_timeframe"), row.get("interval"),
        metrics.get("timeframe"), metrics.get("analysis_timeframe"), metrics.get("interval"),
    )
    return next((_normalize_timeframe(value) for value in values if value not in (None, "")), None)


def _raw_tools(snapshot: Any) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("ai_tools"), dict):
        return None
    raw_tools = snapshot["ai_tools"]
    present_keys = [key for key in AI_TOOL_KEYS if key in raw_tools]
    if (not present_keys or any(not isinstance(raw_tools.get(key), list) for key in present_keys)
            or any(not isinstance(row, dict) for key in present_keys for row in raw_tools.get(key, []))):
        return None
    return raw_tools


def _is_displayable_row(row: dict[str, Any]) -> bool:
    quality = coerce_data_quality(row)
    return (
        quality not in {QUALITY_EMPTY, QUALITY_INVALID, QUALITY_SCORE_ONLY}
        and has_positive_value(row, "price", "close", "last_price")
        and has_positive_value(row, "volume", "last_volume")
    )


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MAX_SNAPSHOT_AGE_SECONDS = max(60, int(os.getenv("AI_SNAPSHOT_MAX_AGE_SECONDS", "300")))
_MAX_AS_OF_AGE_SECONDS = max(60, int(os.getenv("AI_AS_OF_MAX_AGE_SECONDS", "900")))


def _detected_at(row: dict[str, Any]) -> datetime:
    """Time the AI detected the finding, used to order rows most-recent-first."""
    raw = str(row.get("detected_at") or row.get("found_at") or row.get("first_seen_at") or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return _EPOCH
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _confirmed_at(row: dict[str, Any]) -> datetime:
    raw = str(row.get("last_confirmed_at") or row.get("updated_at") or row.get("as_of") or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return _EPOCH
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _snapshot_timestamp(snapshot: dict[str, Any]) -> datetime:
    return _confirmed_at({"updated_at": snapshot.get("updated_at") or snapshot.get("generated_at") or snapshot.get("last_good_timestamp")})


def _row_is_stale(row: dict[str, Any]) -> bool:
    as_of = _confirmed_at({"updated_at": row.get("as_of")})
    return bool(
        coerce_data_quality(row) == QUALITY_STALE
        or row.get("stale") is True
        or row.get("is_stale") is True
        or (as_of != _EPOCH and (datetime.now(timezone.utc) - as_of).total_seconds() > _MAX_AS_OF_AGE_SECONDS)
    )


def _snapshot_is_stale(snapshot: dict[str, Any], *, using_fallback: bool) -> bool:
    data_status = snapshot.get("data_status") if isinstance(snapshot.get("data_status"), dict) else {}
    source = str(snapshot.get("source") or snapshot.get("snapshot_source") or "").lower().strip()
    timestamp = _snapshot_timestamp(snapshot)
    return bool(
        using_fallback
        or snapshot.get("stale") is True
        or snapshot.get("is_stale") is True
        or data_status.get("stale") is True
        or source in {"last_good", "snapshot_fallback", "exception_fallback", "last_good_snapshot"}
        or (timestamp != _EPOCH and (datetime.now(timezone.utc) - timestamp).total_seconds() > _MAX_SNAPSHOT_AGE_SECONDS)
    )


def _scoped_tools(
    raw_tools: dict[str, Any],
    *,
    symbols: tuple[str, ...],
    tool: str | None,
    timeframe: str | None,
    force_non_actionable: bool,
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    normalized_tools = normalize_ai_tools_for_decision_context(raw_tools)
    source_tools = normalized_tools if isinstance(normalized_tools, dict) else {}
    symbol_filter = set(symbols)
    output = _empty_tools()
    actionable_count = 0

    for key in AI_TOOL_KEYS:
        if tool and key != tool:
            continue
        for raw_row in (dict(item) for item in source_tools.get(key, []) if isinstance(item, dict)):
            row_symbol = canonical_symbol(raw_row.get("canonical_symbol") or raw_row.get("symbol") or raw_row.get("ticker"))
            if symbol_filter and row_symbol not in symbol_filter:
                continue
            if timeframe and timeframe != "ALL" and _row_timeframe(raw_row) != timeframe:
                continue
            if not _is_displayable_row(raw_row):
                continue

            row = dict(raw_row)
            if row_symbol:
                row.update({"ticker": row_symbol, "symbol": row_symbol, "canonical_symbol": row_symbol})
            # Contract boundary: every row leaves with a machine key + human label
            # + tone, recomputed from the catalog so snapshots built before this
            # contract (or by any other engine) can never ship a raw English state.
            row["state_key"] = row.get("state_key") or row.get("state")
            row["state_label"], row["tone"] = describe_state(row["state_key"])
            actionable = bool(
                not force_non_actionable
                and row_symbol
                and row.get("can_trade") is True
                and not (row_symbol and symbol_block_reason(row_symbol))
                and is_actionable_snapshot_row(row)
            )
            row["actionable"] = actionable
            if actionable:
                actionable_count += 1
            else:
                row["decision_ready"] = False
                row["can_trade"] = False
            output[key].append(row)
            if len(output[key]) >= AI_ALERT_MAX_ROWS_PER_TOOL:
                break
        # Rows are selected by relevance (score) above, then presented
        # most-recent-first. Stable sort keeps score order within equal times.
        output[key].sort(key=_confirmed_at, reverse=True)
    return output, actionable_count


def _build_payload(
    *,
    status: str,
    reason: str,
    snapshot: dict[str, Any] | None,
    source: str,
    using_fallback: bool,
    tools: dict[str, list[dict[str, Any]]],
    actionable_count: int,
    context: dict[str, Any],
    historical_tools: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    source_snapshot = snapshot if isinstance(snapshot, dict) else {}
    go_live = build_go_live_status(source_snapshot)
    return {
        "reset_key": get_ai_alert_reset_key(),
        "updated_at": source_snapshot.get("updated_at") or source_snapshot.get("generated_at") or source_snapshot.get("last_good_timestamp"),
        "max_rows_per_tool": AI_ALERT_MAX_ROWS_PER_TOOL,
        "reset_hour": AI_ALERT_RESET_HOUR,
        "timezone": str(AI_ALERT_TZ),
        "source": source,
        "using_fallback": using_fallback,
        "go_live_ready": bool(go_live.get("go_live_ready")) and status == "READY",
        "go_live": go_live,
        "institutional_certified": bool(go_live.get("institutional_certified")),
        "institutional_consistency_score": go_live.get("institutional_consistency_score"),
        "contract_coverage": go_live.get("contract_coverage", {}),
        "tools": tools,
        "historical_tools": historical_tools or _empty_tools(),
        "status": status,
        "reason": reason,
        "analyzed_at": context["analyzed_at"],
        "displayable_count": sum(len(rows) for rows in tools.values()),
        "actionable_count": actionable_count,
        "symbol": context["selected_symbol"],
        "selected_symbol": context["selected_symbol"],
        "symbols": list(context["symbols"]),
        "tool": context["selected_tool"],
        "selected_tool": context["selected_tool"],
        "timeframe": context["timeframe"],
        "filters": {
            "symbol": context["selected_symbol"],
            "symbols": list(context["symbols"]),
            "tool": context["selected_tool"],
            "timeframe": context["timeframe"],
        },
    }


def _empty_payload(
    context: dict[str, Any], *, status: str, reason: str, source: str, snapshot: dict[str, Any] | None = None
) -> dict[str, Any]:
    return _build_payload(
        status=status, reason=reason, snapshot=snapshot, source=source, using_fallback=False,
        tools=_empty_tools(), actionable_count=0, context=context,
    )


def _payload_from_snapshot(
    snapshot: dict[str, Any],
    raw_tools: dict[str, Any],
    *,
    context: dict[str, Any],
    using_fallback: bool,
) -> dict[str, Any]:
    stale = _snapshot_is_stale(snapshot, using_fallback=using_fallback)
    tools, actionable_count = _scoped_tools(
        raw_tools,
        symbols=context["symbols"],
        tool=context["selected_tool"],
        timeframe=context["timeframe"],
        force_non_actionable=stale,
    )
    historical_tools = _empty_tools()
    active_tools = _empty_tools()
    for key, rows in tools.items():
        for row in rows:
            if stale or _row_is_stale(row):
                row["freshness_status"] = "HISTORICAL"
                row["actionable"] = False
                row["can_trade"] = False
                row["decision_ready"] = False
                historical_tools[key].append(row)
            else:
                row["freshness_status"] = "READY"
                row.setdefault("last_confirmed_at", row.get("updated_at"))
                row.setdefault("snapshot_generated_at", snapshot.get("generated_at") or snapshot.get("updated_at"))
                active_tools[key].append(row)
    tools = active_tools
    displayable_count = sum(len(rows) for rows in tools.values())
    actionable_count = sum(1 for rows in tools.values() for row in rows if row.get("actionable") is True)
    status = "READY" if displayable_count else "HISTORICAL" if any(historical_tools.values()) else "STALE" if stale else "EMPTY"
    reason = (
        "last_good_snapshot_fallback"
        if using_fallback
        else "snapshot_stale"
        if stale
        else "qualified_findings_available"
        if displayable_count
        else "no_qualified_finding"
    )
    return _build_payload(
        status=status,
        reason=reason,
        snapshot=snapshot,
        source="last_good_snapshot" if using_fallback else "snapshot",
        using_fallback=using_fallback,
        tools=tools,
        actionable_count=actionable_count,
        context=context,
        historical_tools=historical_tools,
    )


def build_public_ai_tools_payload(
    extra_symbols: list[Any] | None = None,
    *,
    symbol: Any = None,
    tool: Any = None,
    timeframe: Any = None,
) -> dict[str, Any]:
    symbols, selected_symbol = _normalize_symbols(extra_symbols, symbol)
    selected_tool = _normalize_tool(tool)
    selected_timeframe = _normalize_timeframe(timeframe)
    context = {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "symbols": symbols,
        "selected_symbol": selected_symbol,
        "selected_tool": selected_tool,
        "timeframe": selected_timeframe,
    }

    filter_error = next((reason for invalid, reason in (
        (symbol not in (None, "") and selected_symbol is None, "invalid_symbol"),
        (tool not in (None, "") and selected_tool is None, "unsupported_tool"),
        (timeframe not in (None, "") and selected_timeframe is None, "invalid_timeframe"),
    ) if invalid), None)
    if filter_error:
        return _empty_payload(context, status="ERROR", reason=filter_error, source="request_error")

    if is_ai_decisions_disabled():
        return _empty_payload(
            context, status="KILL_SWITCHED", reason="kill_switch=DISABLE_AI_DECISIONS", source="kill_switch",
        )

    # A searched symbol is not necessarily part of the global top-N snapshot.
    # Prefer its short-lived worker result; the route only queues this work and
    # never calls a market provider itself.
    if selected_symbol:
        try:
            from app.system.symbol_hydration import get_symbol_analysis, request_symbol_hydration

            request_symbol_hydration(selected_symbol, timeframe=selected_timeframe or "1D")
            on_demand = get_symbol_analysis(selected_symbol, selected_timeframe or "1D")
            on_demand_status = str(on_demand.get("status") or "")
            if on_demand_status == "READY":
                tools, actionable_count = _scoped_tools(
                    on_demand.get("ai_tools") if isinstance(on_demand.get("ai_tools"), dict) else {},
                    symbols=context["symbols"],
                    tool=selected_tool,
                    timeframe=selected_timeframe,
                    force_non_actionable=False,
                )
                return _build_payload(
                    status="READY",
                    reason="on_demand_analysis",
                    snapshot=on_demand,
                    source="on_demand",
                    using_fallback=False,
                    tools=tools,
                    actionable_count=actionable_count,
                    context=context,
                )
            if on_demand_status in {"PENDING", "INSUFFICIENT_DATA", "PROVIDER_ERROR"}:
                return _empty_payload(
                    context,
                    status=on_demand_status,
                    reason=str(on_demand.get("reason") or "on_demand_hydration"),
                    source="on_demand",
                    snapshot=on_demand,
                )
        except Exception:
            logger.exception("On-demand AI hydration enqueue failed for %s", selected_symbol)

    snapshot_error: Exception | None = None
    try:
        snapshot = get_snapshot()
    except Exception as exc:
        snapshot = {}
        snapshot_error = exc
        logger.exception("AI tools current snapshot read failed")

    current_raw_tools = _raw_tools(snapshot)
    if current_raw_tools is not None:
        return _payload_from_snapshot(
            snapshot,
            current_raw_tools,
            context=context,
            using_fallback=False,
        )

    try:
        fallback_snapshot = get_last_good_snapshot()
    except Exception:
        fallback_snapshot = {}
        logger.exception("AI tools last-good snapshot read failed")
    fallback_raw_tools = _raw_tools(fallback_snapshot)
    if fallback_raw_tools is not None:
        fallback_payload = _payload_from_snapshot(
            fallback_snapshot,
            fallback_raw_tools,
            context=context,
            using_fallback=True,
        )
        if fallback_payload["displayable_count"] or any(fallback_payload["historical_tools"].values()):
            return fallback_payload

    status = "ERROR" if snapshot_error is not None else "SNAPSHOT_UNAVAILABLE"
    reason = f"snapshot_read_error:{type(snapshot_error).__name__}" if snapshot_error is not None else "snapshot_unavailable"
    return _empty_payload(
        context, status=status, reason=reason,
        source="snapshot_error" if snapshot_error is not None else "snapshot_unavailable",
        snapshot=snapshot if isinstance(snapshot, dict) else None,
    )
