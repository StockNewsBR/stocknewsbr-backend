from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from app.cache.signal_outcome_cache import get_signal_outcome_state, update_signal_outcome_state
from app.services.snapshot_contract import (
    ACTIONABLE_SIGNALS,
    BLOCKED_DATA_QUALITIES,
    READY_DECISION_STATES,
    audit_status_value,
    build_decision_envelope,
    coerce_data_quality,
    has_blocking_reasons,
    is_actionable_snapshot_row,
    is_auditor_blocked,
    master_confirms_signal,
    master_status_value,
    safe_float,
    snapshot_decision_state,
    snapshot_row_orientation,
    snapshot_signal_value,
)
from app.system.system_metrics import record_signal_outcome_metrics

PAPER_TRADING_MODE = "PAPER_ONLY"
PAPER_TRADING_SIMULATION = "SIMULATED"
MAX_OUTCOME_RECORDS = 5000
SIGNAL_DEDUP_SECONDS = 3900
VALID_OUTCOME_DATA_QUALITIES = {"real_time", "cached"}
OUTCOME_WINDOWS_SECONDS = {"5m": 300, "15m": 900, "30m": 1800, "60m": 3600}
ENTRY_TRADE_ACTIONS = {"BUY", "SHORT"}
NEUTRAL_RETURN_THRESHOLD_PCT = 0.05


def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").strip().upper()


def _price(row: Dict[str, Any]) -> float:
    return safe_float(row.get("price") or row.get("close") or row.get("last_price"), 0.0)


def _volume(row: Dict[str, Any]) -> float:
    return safe_float(row.get("volume") or row.get("last_volume"), 0.0)


def _timestamp(value: Any, default: float) -> float:
    numeric = safe_float(value, 0.0)
    if numeric > 0:
        return numeric
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except ValueError:
            return default
    return default


def _snapshot_timestamp(snapshot: Dict[str, Any], now: float) -> float:
    return _timestamp(
        snapshot.get("generated_at")
        or snapshot.get("updated_at")
        or snapshot.get("timestamp")
        or snapshot.get("snapshot_timestamp"),
        now,
    )


def _row_timestamp(row: Dict[str, Any], fallback: float) -> float:
    return _timestamp(
        row.get("market_data_updated_at")
        or row.get("last_bar_at")
        or row.get("updated_at")
        or row.get("timestamp")
        or row.get("detected_at"),
        fallback,
    )


def _is_stale_snapshot(snapshot: Dict[str, Any]) -> bool:
    runtime = snapshot.get("snapshot_runtime") if isinstance(snapshot.get("snapshot_runtime"), dict) else {}
    status = str(runtime.get("status") or snapshot.get("snapshot_runtime_status") or "").upper()
    return bool(snapshot.get("stale") is True or snapshot.get("is_stale") is True or status == "STALE")


def _is_stale_row(row: Dict[str, Any]) -> bool:
    return bool(row.get("stale") is True or row.get("is_stale") is True or coerce_data_quality(row) == "stale")


def _valid_market_row(row: Dict[str, Any]) -> bool:
    if _is_stale_row(row):
        return False
    if coerce_data_quality(row) not in VALID_OUTCOME_DATA_QUALITIES:
        return False
    return _price(row) > 0


def _intended_direction(row: Dict[str, Any]) -> str:
    signal = snapshot_signal_value(row)
    if signal in {"BUY", "COVER"}:
        return "LONG"
    if signal in {"SELL", "SHORT"}:
        return "SHORT"
    orientation = snapshot_row_orientation(row)
    if orientation == "bullish":
        return "LONG"
    if orientation == "bearish":
        return "SHORT"
    return "UNKNOWN"


def _directional_return_pct(direction: str, entry_price: float, future_price: float) -> float:
    if entry_price <= 0 or future_price <= 0:
        return 0.0
    if direction == "SHORT":
        return round(((entry_price - future_price) / entry_price) * 100.0, 4)
    return round(((future_price - entry_price) / entry_price) * 100.0, 4)


def _score_bucket(row: Dict[str, Any]) -> str:
    score = safe_float(row.get("master_score") or row.get("score"), -1.0)
    if score < 0:
        return "unknown"
    if score >= 80:
        return "80-100"
    if score >= 60:
        return "60-79"
    if score >= 40:
        return "40-59"
    return "0-39"


def _market_regime(row: Dict[str, Any]) -> str:
    for key in ("market_regime", "regime", "chart_regime", "master_regime", "state"):
        value = str(row.get(key) or "").strip().lower()
        if value:
            return value[:64]
    return "unknown"


def _blocking_reason(row: Dict[str, Any], snapshot: Dict[str, Any]) -> str:
    signal = snapshot_signal_value(row)
    if not _symbol(row):
        return "symbol_missing"
    if _is_stale_snapshot(snapshot) or _is_stale_row(row):
        return "stale_data"
    if signal not in ACTIONABLE_SIGNALS:
        return "decision_not_actionable"
    if is_auditor_blocked(row):
        return "auditor_blocked"
    if master_status_value(row) == "BLOCKED":
        return "master_score_blocked"
    if not master_confirms_signal(row):
        return "master_direction_conflict"
    if row.get("decision_ready") is not True:
        return "decision_not_ready"
    decision_state = snapshot_decision_state(row)
    if decision_state and decision_state not in READY_DECISION_STATES:
        return f"decision_state_{decision_state.lower()}"
    quality = coerce_data_quality(row)
    if quality in BLOCKED_DATA_QUALITIES or quality not in VALID_OUTCOME_DATA_QUALITIES:
        return f"data_quality_{quality}"
    if _price(row) <= 0:
        return "invalid_price"
    if _volume(row) <= 0:
        return "invalid_volume"
    if has_blocking_reasons(row):
        return "blocked_reasons"
    return "not_actionable"


def _record_status(actionable: bool, blocking_reason: str, direction: str) -> str:
    if direction == "UNKNOWN" or blocking_reason == "decision_not_actionable":
        return "skipped"
    return "pending" if actionable else "blocked"


def _signal_fingerprint(row: Dict[str, Any], actionable: bool, blocking_reason: str) -> str:
    payload = "|".join(
        [
            _symbol(row),
            snapshot_signal_value(row),
            str(row.get("final_decision") or ""),
            str(row.get("decision_ready") is True),
            str(actionable),
            blocking_reason,
            _score_bucket(row),
            str(row.get("priority_level") or ""),
            str(row.get("conviction_level") or ""),
        ]
    )
    return hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()


def _seen_recent_record(records: Iterable[Dict[str, Any]], fingerprint: str, timestamp: float) -> bool:
    for record in records:
        if str(record.get("fingerprint") or "") != fingerprint:
            continue
        previous = safe_float(record.get("timestamp"), 0.0)
        if previous > 0 and abs(timestamp - previous) < SIGNAL_DEDUP_SECONDS:
            return True
    return False


def _initial_windows() -> Dict[str, Dict[str, Any]]:
    return {label: {"status": "pending"} for label in OUTCOME_WINDOWS_SECONDS}


def _make_record(row: Dict[str, Any], snapshot: Dict[str, Any], snapshot_timestamp: float) -> Dict[str, Any] | None:
    symbol = _symbol(row)
    entry_price = _price(row)
    if not symbol:
        return None

    snapshot_stale = _is_stale_snapshot(snapshot)
    envelope = build_decision_envelope(
        row,
        snapshot_stale=snapshot_stale,
        source_snapshot_id=snapshot.get("snapshot_id") or snapshot.get("generated_at") or snapshot_timestamp,
        timestamp=snapshot_timestamp,
    )
    actionable = False if snapshot_stale else is_actionable_snapshot_row(row)
    blocking_reason = "stale_data" if snapshot_stale else "actionable" if actionable else _blocking_reason(row, snapshot)
    direction = _intended_direction(row)
    timestamp = _row_timestamp(row, snapshot_timestamp)
    fingerprint = _signal_fingerprint(row, actionable, blocking_reason)
    status = _record_status(actionable, blocking_reason, direction)

    return {
        "mode": PAPER_TRADING_MODE,
        "simulation": PAPER_TRADING_SIMULATION,
        "outcome_id": f"{symbol}:{snapshot_signal_value(row) or 'UNKNOWN'}:{int(timestamp * 1000)}:{fingerprint[:10]}",
        "fingerprint": fingerprint,
        "ticker": symbol,
        "timestamp": timestamp,
        "source_snapshot_timestamp": snapshot_timestamp,
        "entry_price": round(entry_price, 6) if entry_price > 0 else None,
        "intended_direction": direction,
        "decision": snapshot_signal_value(row) or "UNKNOWN",
        "decision_status": envelope.get("decision_status"),
        "decision_envelope": envelope,
        "final_decision": row.get("final_decision"),
        "decision_ready": bool(row.get("decision_ready") is True),
        "actionability": bool(actionable),
        "actionability_reason": blocking_reason,
        "master_score": safe_float(row.get("master_score") or row.get("score"), 0.0),
        "score_bucket": _score_bucket(row),
        "priority_level": row.get("priority_level"),
        "conviction_level": row.get("conviction_level") or row.get("master_conviction"),
        "operational_status": row.get("operational_status"),
        "audit_status": audit_status_value(row),
        "historical_confidence": row.get("historical_confidence_score"),
        "market_regime": _market_regime(row),
        "blocking_reason": None if actionable else blocking_reason,
        "paper_trade_executed": bool(actionable and snapshot_signal_value(row) in ENTRY_TRADE_ACTIONS),
        "future_prices": {},
        "windows": _initial_windows(),
        "day_close": {"status": "pending"},
        "observations": [],
        "mfe_pct": None,
        "mae_pct": None,
        "outcome_return_pct": None,
        "simulated_result": "insufficient_data",
        "status": status if status != "pending" else "insufficient_data",
    }


def _is_day_close(snapshot: Dict[str, Any], row: Dict[str, Any]) -> bool:
    for source in (row, snapshot):
        for key in ("is_day_close", "day_close", "session_closed", "market_closed"):
            if source.get(key) is True:
                return True
        status = str(source.get("market_status") or source.get("session_status") or "").strip().lower()
        if status in {"closed", "market_closed", "regular_closed"}:
            return True
    return False


def _add_observation(record: Dict[str, Any], timestamp: float, price: float, return_pct: float) -> None:
    observations = record.setdefault("observations", [])
    if any(abs(safe_float(item.get("timestamp"), 0.0) - timestamp) < 0.001 for item in observations if isinstance(item, dict)):
        return
    observations.append(
        {
            "timestamp": timestamp,
            "price": round(price, 6),
            "return_pct": return_pct,
        }
    )
    record["observations"] = observations[-200:]


def _refresh_record_result(record: Dict[str, Any]) -> None:
    observations = [item for item in record.get("observations", []) if isinstance(item, dict)]
    returns = [safe_float(item.get("return_pct"), 0.0) for item in observations]
    if not returns:
        record["simulated_result"] = "insufficient_data"
        if record.get("actionability") is True:
            record["status"] = "insufficient_data"
        return

    record["mfe_pct"] = round(max(returns), 4)
    record["mae_pct"] = round(min(returns), 4)
    outcome_return = returns[-1]
    record["outcome_return_pct"] = round(outcome_return, 4)

    if outcome_return > NEUTRAL_RETURN_THRESHOLD_PCT:
        result = "winner"
    elif outcome_return < -NEUTRAL_RETURN_THRESHOLD_PCT:
        result = "loser"
    else:
        result = "neutral"

    record["simulated_result"] = result
    if record.get("actionability") is True:
        record["status"] = result
    elif record.get("status") != "skipped":
        record["status"] = "blocked"


def _update_record_from_future_snapshot(record: Dict[str, Any], snapshot: Dict[str, Any], row: Dict[str, Any], snapshot_timestamp: float) -> None:
    if not _valid_market_row(row):
        return

    entry_price = safe_float(record.get("entry_price"), 0.0)
    direction = str(record.get("intended_direction") or "UNKNOWN").upper()
    if entry_price <= 0 or direction not in {"LONG", "SHORT"}:
        return

    future_timestamp = _row_timestamp(row, snapshot_timestamp)
    entry_timestamp = safe_float(record.get("timestamp"), 0.0)
    elapsed = future_timestamp - entry_timestamp
    if elapsed <= 0:
        return

    future_price = _price(row)
    return_pct = _directional_return_pct(direction, entry_price, future_price)
    _add_observation(record, future_timestamp, future_price, return_pct)

    windows = record.setdefault("windows", _initial_windows())
    for label, seconds in OUTCOME_WINDOWS_SECONDS.items():
        current = windows.setdefault(label, {"status": "pending"})
        if current.get("status") == "filled":
            continue
        if elapsed >= seconds:
            current.update(
                {
                    "status": "filled",
                    "timestamp": future_timestamp,
                    "elapsed_seconds": round(elapsed, 2),
                    "price": round(future_price, 6),
                    "return_pct": return_pct,
                }
            )
            record.setdefault("future_prices", {})[label] = round(future_price, 6)

    day_close = record.setdefault("day_close", {"status": "pending"})
    if day_close.get("status") != "filled" and _is_day_close(snapshot, row):
        day_close.update(
            {
                "status": "filled",
                "timestamp": future_timestamp,
                "elapsed_seconds": round(elapsed, 2),
                "price": round(future_price, 6),
                "return_pct": return_pct,
            }
        )
        record.setdefault("future_prices", {})["day_close"] = round(future_price, 6)

    _refresh_record_result(record)


def _group_metrics(records: List[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for record in records:
        value = str(record.get(key) or "unknown")
        entry = grouped.setdefault(value, {"signals": 0, "wins": 0, "losses": 0, "neutral": 0, "avg_return_pct": 0.0, "win_rate": 0.0})
        entry["signals"] += 1
        result = str(record.get("simulated_result") or "")
        if result == "winner":
            entry["wins"] += 1
        elif result == "loser":
            entry["losses"] += 1
        elif result == "neutral":
            entry["neutral"] += 1
        entry["avg_return_pct"] += safe_float(record.get("outcome_return_pct"), 0.0)

    for entry in grouped.values():
        signals = int(entry.get("signals", 0) or 0)
        evaluable = int(entry.get("wins", 0) or 0) + int(entry.get("losses", 0) or 0) + int(entry.get("neutral", 0) or 0)
        entry["avg_return_pct"] = round(float(entry.get("avg_return_pct", 0.0) or 0.0) / max(1, evaluable), 4) if evaluable else 0.0
        entry["win_rate"] = round((int(entry.get("wins", 0) or 0) / max(1, evaluable)) * 100.0, 2) if signals else 0.0
    return grouped


def _drawdown(returns: List[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    return round(max_drawdown, 4)


def calculate_signal_outcome_metrics(state: Dict[str, Any], now: float | None = None) -> Dict[str, Any]:
    records = [record for record in state.get("records", []) if isinstance(record, dict)]
    executable = [record for record in records if record.get("actionability") is True]
    blocked = [record for record in records if record.get("status") == "blocked"]
    skipped = [record for record in records if record.get("status") == "skipped"]
    insufficient = [record for record in records if record.get("simulated_result") == "insufficient_data"]
    evaluated_executable = [record for record in executable if record.get("simulated_result") in {"winner", "loser", "neutral"}]
    winners = [record for record in evaluated_executable if record.get("simulated_result") == "winner"]
    losers = [record for record in evaluated_executable if record.get("simulated_result") == "loser"]
    neutrals = [record for record in evaluated_executable if record.get("simulated_result") == "neutral"]
    blocked_evaluable = [record for record in blocked if record.get("simulated_result") in {"winner", "loser", "neutral"}]
    blocked_winners = [record for record in blocked_evaluable if record.get("simulated_result") == "winner"]
    blocked_correctly = [record for record in blocked_evaluable if record.get("simulated_result") != "winner"]
    returns = [safe_float(record.get("outcome_return_pct"), 0.0) for record in evaluated_executable]
    mfe_values = [safe_float(record.get("mfe_pct"), 0.0) for record in evaluated_executable if record.get("mfe_pct") is not None]
    mae_values = [safe_float(record.get("mae_pct"), 0.0) for record in evaluated_executable if record.get("mae_pct") is not None]
    win_returns = [safe_float(record.get("outcome_return_pct"), 0.0) for record in winners]
    loss_returns = [abs(safe_float(record.get("outcome_return_pct"), 0.0)) for record in losers]
    evaluable_count = len(evaluated_executable)
    total = len(records)

    return {
        "total_signals": total,
        "executable_signals": len(executable),
        "blocked_signals": len(blocked),
        "skipped_signals": len(skipped),
        "insufficient_data": len(insufficient),
        "evaluated_executable_signals": evaluable_count,
        "winner_signals": len(winners),
        "loser_signals": len(losers),
        "neutral_signals": len(neutrals),
        "win_rate": round((len(winners) / max(1, evaluable_count)) * 100.0, 2) if evaluable_count else 0.0,
        "average_mfe_pct": round(sum(mfe_values) / len(mfe_values), 4) if mfe_values else 0.0,
        "average_mae_pct": round(sum(mae_values) / len(mae_values), 4) if mae_values else 0.0,
        "average_payoff": round((sum(win_returns) / len(win_returns)) / max(0.0001, (sum(loss_returns) / len(loss_returns))), 4) if win_returns and loss_returns else 0.0,
        "simulated_drawdown_pct": _drawdown(returns),
        "block_rate": round((len(blocked) / max(1, total)) * 100.0, 2) if total else 0.0,
        "false_positive_rate": round((len(losers) / max(1, evaluable_count)) * 100.0, 2) if evaluable_count else 0.0,
        "false_negative_rate": round((len(blocked_winners) / max(1, len(blocked_evaluable))) * 100.0, 2) if blocked_evaluable else 0.0,
        "insufficient_data_rate": round((len(insufficient) / max(1, total)) * 100.0, 2) if total else 0.0,
        "blocked_would_have_won": len(blocked_winners),
        "blocked_correctly": len(blocked_correctly),
        "released_failed": len(losers),
        "released_won": len(winners),
        "by_symbol": _group_metrics(evaluated_executable, "ticker"),
        "by_regime": _group_metrics(evaluated_executable, "market_regime"),
        "by_score_bucket": _group_metrics(evaluated_executable, "score_bucket"),
        "last_update_timestamp": now if now is not None else state.get("last_update_timestamp"),
    }


def _rows_by_symbol(rows: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
    mapped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = _symbol(row)
        if symbol:
            mapped[symbol] = row
    return mapped


def update_signal_outcome_audit_from_snapshot(snapshot: Dict[str, Any] | None = None, *, now: float | None = None) -> Dict[str, Any]:
    current_time = time.time() if now is None else float(now)
    payload = snapshot if isinstance(snapshot, dict) else {}
    rows = payload.get("signals") if isinstance(payload.get("signals"), list) else []
    snapshot_timestamp = _snapshot_timestamp(payload, current_time)
    state = get_signal_outcome_state()
    state["mode"] = PAPER_TRADING_MODE
    state["simulation"] = PAPER_TRADING_SIMULATION
    state["windows_seconds"] = dict(OUTCOME_WINDOWS_SECONDS)

    row_map = _rows_by_symbol(rows)
    if not _is_stale_snapshot(payload):
        for record in state.get("records", []):
            if not isinstance(record, dict):
                continue
            row = row_map.get(str(record.get("ticker") or "").upper())
            if row:
                _update_record_from_future_snapshot(record, payload, row, snapshot_timestamp)

    for row in rows:
        if not isinstance(row, dict):
            continue
        record = _make_record(row, payload, snapshot_timestamp)
        if not record:
            continue
        if _seen_recent_record(state.get("records", []), str(record.get("fingerprint") or ""), safe_float(record.get("timestamp"), snapshot_timestamp)):
            continue
        state.setdefault("records", []).append(record)

    state["records"] = [record for record in state.get("records", []) if isinstance(record, dict)][-MAX_OUTCOME_RECORDS:]
    state["last_update_timestamp"] = current_time
    state["metrics"] = calculate_signal_outcome_metrics(state, now=current_time)
    state["signal_outcome_status"] = "HEALTHY" if rows else "IDLE"
    record_signal_outcome_metrics(state["metrics"])
    return update_signal_outcome_state(state)


def get_signal_outcome_audit_status() -> Dict[str, Any]:
    state = get_signal_outcome_state()
    state["mode"] = PAPER_TRADING_MODE
    state["simulation"] = PAPER_TRADING_SIMULATION
    state["metrics"] = calculate_signal_outcome_metrics(state, now=state.get("last_update_timestamp"))
    record_signal_outcome_metrics(state["metrics"])
    return state
