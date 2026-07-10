from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from app.cache.paper_trading_cache import get_paper_trading_state, update_paper_trading_state
from app.cache.snapshot_cache import get_snapshot
from app.services.snapshot_contract import coerce_data_quality, is_auditor_blocked, safe_float

PAPER_TRADING_MODE = "PAPER_ONLY"
PAPER_TRADING_SIMULATION = "SIMULATED"
MAX_SKIPPED_HISTORY = 500
MAX_CLOSED_TRADES_HISTORY = 1000
VALID_DATA_QUALITIES = {"real_time", "cached"}
ENTRY_DECISIONS = {"BUY", "SHORT"}
CLOSE_LONG_DECISIONS = {"SELL", "EXIT", "CLOSE"}
CLOSE_SHORT_DECISIONS = {"COVER", "EXIT", "CLOSE"}
PASSIVE_DECISIONS = {"NO_TRADE", "DO_NOT_TRADE", "WAIT", "HOLD", "WATCH"}


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _enabled() -> bool:
    return _env_flag("PAPER_TRADING_ENABLED", True)


def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").strip().upper()


def _decision(row: Dict[str, Any]) -> str:
    return str(row.get("trade_action") or row.get("signal") or row.get("action") or "").strip().upper()


def _price(row: Dict[str, Any]) -> float:
    return safe_float(row.get("price") or row.get("close") or row.get("last_price"), 0.0)


def _volume(row: Dict[str, Any]) -> float:
    return safe_float(row.get("volume") or row.get("last_volume"), 0.0)


def _snapshot_timestamp(snapshot: Dict[str, Any], now: float) -> float:
    for raw_value in (
        snapshot.get("generated_at"),
        snapshot.get("updated_at"),
        snapshot.get("timestamp"),
    ):
        numeric_value = safe_float(raw_value, 0.0)
        if numeric_value > 0:
            return numeric_value

        if isinstance(raw_value, str):
            normalized = raw_value.strip()
            if normalized:
                try:
                    parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    timestamp = parsed.astimezone(timezone.utc).timestamp()
                    if timestamp > 0:
                        return timestamp
                except (ValueError, OSError, OverflowError):
                    pass

    return now


def _snapshot_is_stale(snapshot: Dict[str, Any]) -> bool:
    return bool(snapshot.get("stale") is True or snapshot.get("is_stale") is True)


def _final_decision_blocks(row: Dict[str, Any]) -> bool:
    final_decision = str(row.get("final_decision") or "").upper()
    operational_status = str(row.get("operational_status") or "").upper()
    audit_status = str(row.get("audit_status") or row.get("auditor_status") or "").upper()
    if "NÃO OPERAR" in final_decision or "NAO OPERAR" in final_decision:
        return True
    if "NO_TRADE" in final_decision or "DO_NOT_TRADE" in final_decision:
        return True
    if operational_status == "BLOCKED" or audit_status == "BLOCKED":
        return True
    blocks = row.get("final_decision_blocks") or row.get("operational_blocks") or []
    if isinstance(blocks, str):
        return bool(blocks.strip())
    if isinstance(blocks, (list, tuple, set)):
        return any(str(item).strip() for item in blocks)
    return bool(blocks)


def _base_skip_reason(row: Dict[str, Any], snapshot: Dict[str, Any]) -> str | None:
    if not _symbol(row):
        return "symbol_missing"
    if _snapshot_is_stale(snapshot) or row.get("stale") is True or row.get("is_stale") is True:
        return "snapshot_stale"
    if is_auditor_blocked(row):
        return "auditor_blocked"
    if row.get("decision_ready") is not True:
        return "decision_not_ready"
    quality = coerce_data_quality(row)
    if quality not in VALID_DATA_QUALITIES:
        return f"data_quality_{quality}"
    if _price(row) <= 0:
        return "invalid_price"
    if _volume(row) <= 0:
        return "invalid_volume"
    if _final_decision_blocks(row):
        return "final_decision_blocked"
    return None


def _append_skip(
    state: Dict[str, Any],
    row: Dict[str, Any],
    decision: str,
    reason: str,
    now: float,
    snapshot_timestamp: float,
) -> None:
    state.setdefault("skipped", []).append(
        {
            "mode": PAPER_TRADING_MODE,
            "simulation": PAPER_TRADING_SIMULATION,
            "symbol": _symbol(row),
            "decision": decision,
            "skipped_reason": reason,
            "timestamp": now,
            "source_snapshot_timestamp": snapshot_timestamp,
        }
    )
    state["skipped"] = state["skipped"][-MAX_SKIPPED_HISTORY:]


def _open_positions(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        position
        for position in state.get("positions", [])
        if isinstance(position, dict) and str(position.get("status") or "").upper() == "OPEN"
    ]


def _find_open_position(state: Dict[str, Any], symbol: str, side: str) -> Dict[str, Any] | None:
    for position in _open_positions(state):
        if str(position.get("symbol") or "").upper() == symbol and str(position.get("side") or "").upper() == side:
            return position
    return None


def _return_pct(side: str, entry_price: float, exit_price: float) -> float:
    if entry_price <= 0:
        return 0.0
    if side == "SHORT":
        return round(((entry_price - exit_price) / entry_price) * 100.0, 4)
    return round(((exit_price - entry_price) / entry_price) * 100.0, 4)


def _open_position(
    state: Dict[str, Any],
    row: Dict[str, Any],
    side: str,
    now: float,
    snapshot_timestamp: float,
) -> None:
    symbol = _symbol(row)
    position = {
        "mode": PAPER_TRADING_MODE,
        "simulation": PAPER_TRADING_SIMULATION,
        "position_id": f"{symbol}:{side}:{int(now * 1000)}",
        "symbol": symbol,
        "side": side,
        "entry_price": round(_price(row), 6),
        "entry_timestamp": now,
        "entry_decision": _decision(row),
        "entry_final_decision": row.get("final_decision"),
        "confidence": row.get("confidence") or row.get("final_decision_confidence"),
        "conviction": row.get("conviction_level") or row.get("master_conviction"),
        "source_snapshot_timestamp": snapshot_timestamp,
        "status": "OPEN",
    }
    state.setdefault("positions", []).append(position)


def _close_position(
    state: Dict[str, Any],
    position: Dict[str, Any],
    row: Dict[str, Any],
    now: float,
    snapshot_timestamp: float,
) -> None:
    exit_price = round(_price(row), 6)
    side = str(position.get("side") or "").upper()
    entry_price = safe_float(position.get("entry_price"), 0.0)
    return_pct = _return_pct(side, entry_price, exit_price)
    position.update(
        {
            "status": "CLOSED",
            "exit_price": exit_price,
            "exit_timestamp": now,
            "exit_decision": _decision(row),
            "exit_final_decision": row.get("final_decision"),
            "return_pct": return_pct,
        }
    )
    state.setdefault("trades", []).append(
        {
            "mode": PAPER_TRADING_MODE,
            "simulation": PAPER_TRADING_SIMULATION,
            "position_id": position.get("position_id"),
            "symbol": position.get("symbol"),
            "side": side,
            "entry_price": entry_price,
            "entry_timestamp": position.get("entry_timestamp"),
            "entry_decision": position.get("entry_decision"),
            "exit_price": exit_price,
            "exit_timestamp": now,
            "exit_decision": _decision(row),
            "return_pct": return_pct,
            "source_snapshot_timestamp": snapshot_timestamp,
            "status": "CLOSED",
        }
    )
    state["trades"] = state["trades"][-MAX_CLOSED_TRADES_HISTORY:]


def calculate_paper_trading_metrics(state: Dict[str, Any], now: float | None = None) -> Dict[str, Any]:
    positions = [position for position in state.get("positions", []) if isinstance(position, dict)]
    open_positions = [position for position in positions if str(position.get("status") or "").upper() == "OPEN"]
    trades = [trade for trade in state.get("trades", []) if isinstance(trade, dict)]
    skipped = [item for item in state.get("skipped", []) if isinstance(item, dict)]
    returns = [safe_float(trade.get("return_pct"), 0.0) for trade in trades]
    wins = [value for value in returns if value > 0]
    skipped_reasons: Dict[str, int] = {}
    for item in skipped:
        reason = str(item.get("skipped_reason") or "unknown")
        skipped_reasons[reason] = int(skipped_reasons.get(reason, 0)) + 1

    return {
        "total_trades": len(open_positions) + len(trades),
        "open_trades": len(open_positions),
        "closed_trades": len(trades),
        "win_rate": round((len(wins) / len(trades)) * 100.0, 2) if trades else 0.0,
        "avg_return_pct": round(sum(returns) / len(returns), 4) if returns else 0.0,
        "total_return_pct": round(sum(returns), 4) if returns else 0.0,
        "max_win_pct": round(max(returns), 4) if returns else 0.0,
        "max_loss_pct": round(min(returns), 4) if returns else 0.0,
        "skipped_signals": len(skipped),
        "skipped_reasons": skipped_reasons,
        "last_update_timestamp": now if now is not None else state.get("last_update_timestamp"),
    }


def _process_row(state: Dict[str, Any], row: Dict[str, Any], snapshot: Dict[str, Any], now: float, snapshot_timestamp: float) -> None:
    decision = _decision(row)
    if decision in PASSIVE_DECISIONS or not decision:
        _append_skip(state, row, decision or "UNKNOWN", "decision_not_actionable", now, snapshot_timestamp)
        return

    skip_reason = _base_skip_reason(row, snapshot)
    if skip_reason:
        _append_skip(state, row, decision, skip_reason, now, snapshot_timestamp)
        return

    symbol = _symbol(row)
    if decision == "BUY":
        if _find_open_position(state, symbol, "LONG"):
            _append_skip(state, row, decision, "existing_open_position", now, snapshot_timestamp)
            return
        if _find_open_position(state, symbol, "SHORT"):
            _append_skip(state, row, decision, "opposite_position_open", now, snapshot_timestamp)
            return
        _open_position(state, row, "LONG", now, snapshot_timestamp)
        return

    if decision == "SHORT":
        if _find_open_position(state, symbol, "SHORT"):
            _append_skip(state, row, decision, "existing_open_position", now, snapshot_timestamp)
            return
        if _find_open_position(state, symbol, "LONG"):
            _append_skip(state, row, decision, "opposite_position_open", now, snapshot_timestamp)
            return
        _open_position(state, row, "SHORT", now, snapshot_timestamp)
        return

    if decision in CLOSE_LONG_DECISIONS:
        position = _find_open_position(state, symbol, "LONG")
        if position:
            _close_position(state, position, row, now, snapshot_timestamp)
            return
        if decision not in CLOSE_SHORT_DECISIONS:
            _append_skip(state, row, decision, "no_open_long_position", now, snapshot_timestamp)
            return
        # Mission 31G: EXIT/CLOSE are side-agnostic - fall through to the SHORT leg
        # so an open short is never left dangling as "no_open_long_position".

    if decision in CLOSE_SHORT_DECISIONS:
        position = _find_open_position(state, symbol, "SHORT")
        if not position:
            reason = "no_open_position" if decision in CLOSE_LONG_DECISIONS else "no_open_short_position"
            _append_skip(state, row, decision, reason, now, snapshot_timestamp)
            return
        _close_position(state, position, row, now, snapshot_timestamp)
        return

    _append_skip(state, row, decision, "unsupported_decision", now, snapshot_timestamp)


def update_paper_trading_from_snapshot(snapshot: Dict[str, Any] | None = None, *, now: float | None = None) -> Dict[str, Any]:
    current_time = time.time() if now is None else float(now)
    state = get_paper_trading_state()
    state["mode"] = PAPER_TRADING_MODE
    state["simulation"] = PAPER_TRADING_SIMULATION
    state["paper_trading_enabled"] = _enabled()

    if not state["paper_trading_enabled"]:
        state["paper_trading_status"] = "DISABLED"
        state["last_update_timestamp"] = current_time
        state["metrics"] = calculate_paper_trading_metrics(state, now=current_time)
        return update_paper_trading_state(state)

    payload = snapshot if isinstance(snapshot, dict) else get_snapshot()
    if not isinstance(payload, dict):
        payload = {}
    rows = payload.get("signals") if isinstance(payload.get("signals"), list) else []
    snapshot_timestamp = _snapshot_timestamp(payload, current_time)

    for row in rows:
        if isinstance(row, dict):
            _process_row(state, row, payload, current_time, snapshot_timestamp)

    state["last_update_timestamp"] = current_time
    state["metrics"] = calculate_paper_trading_metrics(state, now=current_time)
    state["paper_trading_status"] = "HEALTHY" if rows else "IDLE"
    return update_paper_trading_state(state)


def get_paper_trading_status() -> Dict[str, Any]:
    state = get_paper_trading_state()
    state["mode"] = PAPER_TRADING_MODE
    state["simulation"] = PAPER_TRADING_SIMULATION
    state["paper_trading_enabled"] = _enabled()
    if not state["paper_trading_enabled"]:
        state["paper_trading_status"] = "DISABLED"
    state["metrics"] = calculate_paper_trading_metrics(state, now=state.get("last_update_timestamp"))
    metrics = state["metrics"]
    state.update(
        {
            "total_trades": metrics["total_trades"],
            "open_trades": metrics["open_trades"],
            "closed_trades": metrics["closed_trades"],
            "win_rate": metrics["win_rate"],
            "total_return_pct": metrics["total_return_pct"],
            "skipped_signals": metrics["skipped_signals"],
            "last_update_timestamp": metrics["last_update_timestamp"],
        }
    )
    return state


def summarize_paper_trading_status(state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = state if isinstance(state, dict) else get_paper_trading_status()
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    return {
        "mode": PAPER_TRADING_MODE,
        "simulation": PAPER_TRADING_SIMULATION,
        "paper_trading_enabled": bool(payload.get("paper_trading_enabled")),
        "paper_trading_status": payload.get("paper_trading_status") or "IDLE",
        "total_trades": int(metrics.get("total_trades", 0) or 0),
        "open_trades": int(metrics.get("open_trades", 0) or 0),
        "closed_trades": int(metrics.get("closed_trades", 0) or 0),
        "win_rate": float(metrics.get("win_rate", 0.0) or 0.0),
        "total_return_pct": float(metrics.get("total_return_pct", 0.0) or 0.0),
        "skipped_signals": int(metrics.get("skipped_signals", 0) or 0),
        "last_update_timestamp": metrics.get("last_update_timestamp"),
    }


def update_paper_trading_batch(rows: Iterable[Dict[str, Any]], *, now: float | None = None) -> Dict[str, Any]:
    return update_paper_trading_from_snapshot({"signals": list(rows or []), "stale": False}, now=now)
