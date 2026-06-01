from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from app.engine.trend_breakout_signal_engine import build_trend_breakout_payload

logger = logging.getLogger("stocknewsbr.backtest")

ENTRY_EVENTS = {"BUY": "long", "SHORT": "short"}
EXIT_EVENTS = {"SELL": "long", "COVER": "short"}


def _row_value(row: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in row:
            return row.get(key)
    return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_ohlc_rows(ohlc: Sequence[Mapping[str, Any]] | None) -> tuple[List[Dict[str, Any]], int]:
    rows: List[Dict[str, Any]] = []
    dropped = 0

    for index, source_row in enumerate(ohlc or []):
        if not isinstance(source_row, Mapping):
            dropped += 1
            continue

        close = _safe_float(_row_value(source_row, "close", "Close"))
        if close <= 0:
            dropped += 1
            continue

        open_price = _safe_float(_row_value(source_row, "open", "Open"), close)
        high = _safe_float(_row_value(source_row, "high", "High"), max(open_price, close))
        low = _safe_float(_row_value(source_row, "low", "Low"), min(open_price, close))
        volume = _safe_float(_row_value(source_row, "volume", "Volume"))

        high = max(high, open_price, close)
        low = min(low, open_price, close)

        rows.append(
            {
                "time": _row_value(source_row, "time", "Time", "date", "Date", default=f"bar_{index:04d}"),
                "open": round(open_price, 6),
                "high": round(high, 6),
                "low": round(low, 6),
                "close": round(close, 6),
                "volume": max(0.0, volume),
            }
        )

    return rows, dropped


def _event_key(event: Mapping[str, Any]) -> tuple[str, str, float, str]:
    return (
        str(event.get("type") or "").upper(),
        str(event.get("time") or ""),
        round(_safe_float(event.get("price")), 6),
        str(event.get("reason") or ""),
    )


def _event_bar_index(event: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], fallback: int) -> int:
    event_time = str(event.get("time") or "")
    for index, row in enumerate(rows):
        if str(row.get("time") or "") == event_time:
            return index
    return max(0, min(fallback, len(rows) - 1))


def _trade_pnl_pct(side: str, entry_price: float, exit_price: float) -> float:
    if entry_price <= 0 or exit_price <= 0:
        return 0.0
    if side == "short":
        return ((entry_price - exit_price) / entry_price) * 100
    return ((exit_price - entry_price) / entry_price) * 100


def _excursion_pct(side: str, entry_price: float, bars: Sequence[Mapping[str, Any]]) -> tuple[float, float]:
    if entry_price <= 0 or not bars:
        return 0.0, 0.0

    lows = [_safe_float(row.get("low"), entry_price) for row in bars]
    highs = [_safe_float(row.get("high"), entry_price) for row in bars]

    if side == "short":
        adverse = ((max(highs) - entry_price) / entry_price) * 100
        favorable = ((entry_price - min(lows)) / entry_price) * 100
    else:
        adverse = ((entry_price - min(lows)) / entry_price) * 100
        favorable = ((max(highs) - entry_price) / entry_price) * 100

    return round(max(0.0, adverse), 4), round(max(0.0, favorable), 4)


def _build_trade(
    *,
    side: str,
    entry_event: Mapping[str, Any],
    exit_event: Mapping[str, Any],
    entry_index: int,
    exit_index: int,
    rows: Sequence[Mapping[str, Any]],
    status: str,
) -> Dict[str, Any]:
    entry_price = _safe_float(entry_event.get("price"))
    exit_price = _safe_float(exit_event.get("price"))
    pnl_pct = _trade_pnl_pct(side, entry_price, exit_price)
    held_bars = max(0, exit_index - entry_index)
    trade_rows = rows[entry_index : exit_index + 1] if rows else []
    adverse, favorable = _excursion_pct(side, entry_price, trade_rows)

    return {
        "side": side,
        "status": status,
        "entry_time": entry_event.get("time"),
        "entry_price": round(entry_price, 4),
        "entry_event_type": str(entry_event.get("type") or "").upper(),
        "entry_reason": entry_event.get("reason"),
        "entry_confidence": entry_event.get("confidence"),
        "exit_time": exit_event.get("time"),
        "exit_price": round(exit_price, 4),
        "exit_event_type": str(exit_event.get("type") or "").upper(),
        "exit_reason": exit_event.get("reason"),
        "exit_confidence": exit_event.get("confidence"),
        "bars_held": held_bars,
        "pnl_pct": round(pnl_pct, 4),
        "pnl_abs": round(exit_price - entry_price if side == "long" else entry_price - exit_price, 4),
        "max_adverse_excursion_pct": adverse,
        "max_favorable_excursion_pct": favorable,
        "coherence_status": exit_event.get("coherence_status") or entry_event.get("coherence_status"),
        "risk_level": exit_event.get("risk_level") or entry_event.get("risk_level"),
    }


def _summarize_trades(trades: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    realized = [trade for trade in trades if trade.get("status") == "closed"]
    marked = list(trades)
    realized_pnls = [_safe_float(trade.get("pnl_pct")) for trade in realized]
    marked_pnls = [_safe_float(trade.get("pnl_pct")) for trade in marked]
    wins = [pnl for pnl in realized_pnls if pnl > 0]
    losses = [pnl for pnl in realized_pnls if pnl < 0]

    if realized_pnls:
        best_trade = max(realized_pnls)
        worst_trade = min(realized_pnls)
        avg_trade = sum(realized_pnls) / len(realized_pnls)
    else:
        best_trade = worst_trade = avg_trade = 0.0

    return {
        "total_trades": len(marked),
        "closed_trades": len(realized),
        "open_trades": len(marked) - len(realized),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round((len(wins) / len(realized) * 100), 2) if realized else 0.0,
        "net_return_pct": round(sum(realized_pnls), 4),
        "marked_return_pct": round(sum(marked_pnls), 4),
        "gross_profit_pct": round(sum(wins), 4),
        "gross_loss_pct": round(sum(losses), 4),
        "expectancy_pct": round(avg_trade, 4),
        "best_trade_pct": round(best_trade, 4),
        "worst_trade_pct": round(worst_trade, 4),
        "max_adverse_excursion_pct": round(max((_safe_float(t.get("max_adverse_excursion_pct")) for t in marked), default=0.0), 4),
        "max_favorable_excursion_pct": round(max((_safe_float(t.get("max_favorable_excursion_pct")) for t in marked), default=0.0), 4),
    }


def _simulate_trades(events: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    trades: List[Dict[str, Any]] = []
    open_trade: Dict[str, Any] | None = None

    for fallback_index, event in enumerate(events):
        event_type = str(event.get("type") or "").upper()
        event_index = _event_bar_index(event, rows, fallback_index)

        if event_type in ENTRY_EVENTS:
            if open_trade is not None:
                continue
            open_trade = {
                "side": ENTRY_EVENTS[event_type],
                "event": dict(event),
                "index": event_index,
            }
            continue

        if event_type not in EXIT_EVENTS or open_trade is None:
            continue

        if EXIT_EVENTS[event_type] != open_trade["side"]:
            continue

        trades.append(
            _build_trade(
                side=open_trade["side"],
                entry_event=open_trade["event"],
                exit_event=event,
                entry_index=open_trade["index"],
                exit_index=event_index,
                rows=rows,
                status="closed",
            )
        )
        open_trade = None

    if open_trade is not None and rows:
        last_index = len(rows) - 1
        last_row = rows[last_index]
        mark_event = {
            "type": "MARK_TO_MARKET",
            "time": last_row.get("time"),
            "price": last_row.get("close"),
            "reason": "open_position",
            "confidence": open_trade["event"].get("confidence"),
            "coherence_status": open_trade["event"].get("coherence_status"),
            "risk_level": open_trade["event"].get("risk_level"),
        }
        trades.append(
            _build_trade(
                side=open_trade["side"],
                entry_event=open_trade["event"],
                exit_event=mark_event,
                entry_index=open_trade["index"],
                exit_index=last_index,
                rows=rows,
                status="open",
            )
        )

    return trades


def _collect_replay_events(
    symbol: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    timeframe: str,
    ai_context: Dict[str, Any] | None,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    seen = set()
    events: List[Dict[str, Any]] = []
    latest_payload: Dict[str, Any] | None = None

    if not rows:
        return [], build_trend_breakout_payload(symbol, [], timeframe=timeframe, ai_context=ai_context)

    for end_index in range(1, len(rows) + 1):
        latest_payload = build_trend_breakout_payload(
            symbol,
            list(rows[:end_index]),
            timeframe=timeframe,
            ai_context=ai_context,
        )

        for event in latest_payload.get("events", []):
            event_type = str(event.get("type") or "").upper()
            if event_type not in ENTRY_EVENTS and event_type not in EXIT_EVENTS:
                continue

            key = _event_key(event)
            if key in seen:
                continue

            seen.add(key)
            events.append(dict(event))

    return events, latest_payload or build_trend_breakout_payload(symbol, rows, timeframe=timeframe, ai_context=ai_context)


def replay_trading_scenario(
    symbol: str,
    ohlc: Sequence[Mapping[str, Any]] | None,
    *,
    timeframe: str = "5m",
    ai_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    rows, dropped = _normalize_ohlc_rows(ohlc)
    events, payload = _collect_replay_events(symbol, rows, timeframe=timeframe, ai_context=ai_context)
    trades = _simulate_trades(events, rows)

    return {
        "symbol": payload.get("symbol") or symbol,
        "ticker": payload.get("ticker") or symbol,
        "engine": payload.get("engine") or "trend_breakout_v1",
        "timeframe": payload.get("timeframe") or timeframe,
        "signal": payload.get("signal", "NEUTRAL"),
        "score": payload.get("score", 0),
        "trend": payload.get("trend", "sideways"),
        "data_quality": {
            "status": "valid" if rows and payload.get("context", {}).get("reason") != "insufficient_data" else "insufficient_data",
            "bars_received": len(ohlc or []),
            "bars_used": len(rows),
            "dropped_bars": dropped,
        },
        "events": events,
        "latest_event": events[-1] if events else None,
        "trades": trades,
        "metrics": _summarize_trades(trades),
        "context": payload.get("context", {}),
    }


def backtest_trading_scenarios(scenarios: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    results: Dict[str, Any] = {}

    for scenario in scenarios or []:
        if not isinstance(scenario, Mapping):
            continue

        symbol = str(scenario.get("symbol") or scenario.get("ticker") or "").strip()
        if not symbol:
            continue

        results[symbol] = replay_trading_scenario(
            symbol,
            scenario.get("ohlc") or scenario.get("bars") or [],
            timeframe=str(scenario.get("timeframe") or "5m"),
            ai_context=scenario.get("ai_context") if isinstance(scenario.get("ai_context"), dict) else None,
        )

    return results


def backtest_portfolio(tickers):
    if not tickers:
        return {}

    try:
        import yfinance as yf
        import pandas as pd

        data = yf.download(
            tickers=tickers,
            period="1y",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False,
            timeout=8,
        )

        if data is None or data.empty:
            return {}

        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"]
        else:
            close = pd.DataFrame({tickers[0]: data["Close"]})

        performance = {}

        for ticker in close.columns:
            try:
                series = close[ticker].dropna()

                if len(series) < 2:
                    continue

                start = series.iloc[0]
                end = series.iloc[-1]
                pct = ((end - start) / start) * 100
                performance[ticker] = round(pct, 2)
            except Exception as exc:
                logger.warning("Backtest error %s: %s", ticker, exc)

        return performance
    except Exception as exc:
        logger.error("Backtest engine failure: %s", exc)
        return {}
