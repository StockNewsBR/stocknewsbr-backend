from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from app.engine.trend_breakout_signal_engine import build_trend_breakout_payload

logger = logging.getLogger("stocknewsbr.backtest")

ENTRY_EVENTS = {"BUY": "long", "SHORT": "short"}
EXIT_EVENTS = {"SELL": "long", "COVER": "short"}
LATERAL_REGIME_STATES = {"chop", "range", "squeeze", "sideways", "lateral"}
OVERTRADING_MIN_LATERAL_TRADES = 3
OVERTRADING_MAX_LATERAL_ENTRIES_PER_100_BARS = 4.0


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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_state(value: Any) -> str:
    return str(value or "").strip().lower() or "unknown"


def _as_list(value: Any) -> List[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _is_lateral_regime(value: Any) -> bool:
    return _normalize_state(value) in LATERAL_REGIME_STATES


def _trade_entry_regime(trade: Mapping[str, Any]) -> str:
    return _normalize_state(
        trade.get("entry_chart_regime_state")
        or trade.get("chart_regime_state")
        or trade.get("entry_market_regime_state")
    )


def _rate_per_100(count: int, bars_count: int) -> float:
    if bars_count <= 0:
        return 0.0
    return round((count / bars_count) * 100, 4)


def _average(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _normalize_regime_counts(regime_bar_counts: Mapping[str, Any] | None) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for regime, count in (regime_bar_counts or {}).items():
        normalized = _normalize_state(regime)
        counts[normalized] = counts.get(normalized, 0) + max(0, _safe_int(count))
    return counts


def _lateral_bars_count(regime_bar_counts: Mapping[str, Any] | None) -> int:
    return sum(count for regime, count in _normalize_regime_counts(regime_bar_counts).items() if _is_lateral_regime(regime))


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
        "entry_chart_regime_state": entry_event.get("chart_regime_state"),
        "entry_liquidity_event": entry_event.get("liquidity_event"),
        "entry_blocked_reasons": _as_list(entry_event.get("blocked_reasons")),
        "entry_warnings": _as_list(entry_event.get("warnings")),
        "exit_time": exit_event.get("time"),
        "exit_price": round(exit_price, 4),
        "exit_event_type": str(exit_event.get("type") or "").upper(),
        "exit_reason": exit_event.get("reason"),
        "exit_confidence": exit_event.get("confidence"),
        "exit_chart_regime_state": exit_event.get("chart_regime_state"),
        "exit_liquidity_event": exit_event.get("liquidity_event"),
        "exit_blocked_reasons": _as_list(exit_event.get("blocked_reasons")),
        "exit_warnings": _as_list(exit_event.get("warnings")),
        "bars_held": held_bars,
        "pnl_pct": round(pnl_pct, 4),
        "pnl_abs": round(exit_price - entry_price if side == "long" else entry_price - exit_price, 4),
        "max_adverse_excursion_pct": adverse,
        "max_favorable_excursion_pct": favorable,
        "coherence_status": exit_event.get("coherence_status") or entry_event.get("coherence_status"),
        "risk_level": exit_event.get("risk_level") or entry_event.get("risk_level"),
    }


def _basic_trade_summary(trades: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
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


def _measure_lateral_overtrading(
    trades: Sequence[Mapping[str, Any]],
    *,
    bars_count: int,
    regime_bar_counts: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    lateral_trades = [trade for trade in trades if _is_lateral_regime(_trade_entry_regime(trade))]
    lateral_closed = [trade for trade in lateral_trades if trade.get("status") == "closed"]
    lateral_realized_pnls = [_safe_float(trade.get("pnl_pct")) for trade in lateral_closed]
    lateral_marked_pnls = [_safe_float(trade.get("pnl_pct")) for trade in lateral_trades]
    lateral_bars = _lateral_bars_count(regime_bar_counts)
    denominator_bars = lateral_bars if lateral_bars > 0 else max(0, bars_count)
    entry_rate = _rate_per_100(len(lateral_trades), denominator_bars)
    realized_expectancy = _average(lateral_realized_pnls)
    marked_expectancy = _average(lateral_marked_pnls)
    expectancy_for_status = realized_expectancy if lateral_closed else marked_expectancy

    if not trades:
        status = "no_trades"
    elif not lateral_trades:
        status = "ok"
    elif (
        len(lateral_trades) >= OVERTRADING_MIN_LATERAL_TRADES
        and entry_rate > OVERTRADING_MAX_LATERAL_ENTRIES_PER_100_BARS
        and expectancy_for_status <= 0
    ):
        status = "overtrading"
    elif len(lateral_trades) >= OVERTRADING_MIN_LATERAL_TRADES or expectancy_for_status < 0:
        status = "watch"
    else:
        status = "ok"

    return {
        "status": status,
        "lateral_trades": len(lateral_trades),
        "lateral_closed_trades": len(lateral_closed),
        "lateral_bars": lateral_bars,
        "lateral_entry_rate_per_100_bars": entry_rate,
        "lateral_net_return_pct": round(sum(lateral_realized_pnls), 4),
        "lateral_marked_return_pct": round(sum(lateral_marked_pnls), 4),
        "lateral_expectancy_pct": round(realized_expectancy, 4),
        "lateral_marked_expectancy_pct": round(marked_expectancy, 4),
        "min_lateral_trades": OVERTRADING_MIN_LATERAL_TRADES,
        "max_lateral_entries_per_100_bars": OVERTRADING_MAX_LATERAL_ENTRIES_PER_100_BARS,
    }


def _summarize_trades(
    trades: Sequence[Mapping[str, Any]],
    *,
    bars_count: int = 0,
    regime_bar_counts: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    summary = _basic_trade_summary(trades)
    summary["long_trades"] = sum(1 for trade in trades if trade.get("side") == "long")
    summary["short_trades"] = sum(1 for trade in trades if trade.get("side") == "short")
    summary["avg_bars_held"] = round(_average([_safe_float(trade.get("bars_held")) for trade in trades]), 4)
    summary["trade_rate_per_100_bars"] = _rate_per_100(len(trades), bars_count)
    summary["lateral_trades"] = sum(1 for trade in trades if _is_lateral_regime(_trade_entry_regime(trade)))
    summary["overtrading"] = _measure_lateral_overtrading(
        trades,
        bars_count=bars_count,
        regime_bar_counts=regime_bar_counts,
    )
    return summary


def _summarize_trades_by_entry_regime(
    trades: Sequence[Mapping[str, Any]],
    *,
    regime_bar_counts: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    grouped: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    normalized_counts = _normalize_regime_counts(regime_bar_counts)

    for trade in trades:
        grouped[_trade_entry_regime(trade)].append(trade)

    summaries: Dict[str, Any] = {}
    for regime in sorted(grouped):
        regime_trades = grouped[regime]
        regime_bars = normalized_counts.get(regime, 0)
        summary = _basic_trade_summary(regime_trades)
        summary["bars"] = regime_bars
        summary["bucket"] = "lateral" if _is_lateral_regime(regime) else "directional"
        summary["trade_rate_per_100_bars"] = _rate_per_100(len(regime_trades), regime_bars)
        summaries[regime] = summary

    return summaries


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
) -> tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, int]]:
    seen = set()
    events: List[Dict[str, Any]] = []
    latest_payload: Dict[str, Any] | None = None
    regime_bar_counts: Dict[str, int] = {}

    if not rows:
        return [], build_trend_breakout_payload(symbol, [], timeframe=timeframe, ai_context=ai_context), regime_bar_counts

    for end_index in range(1, len(rows) + 1):
        latest_payload = build_trend_breakout_payload(
            symbol,
            list(rows[:end_index]),
            timeframe=timeframe,
            ai_context=ai_context,
        )
        regime = _normalize_state(latest_payload.get("context", {}).get("chart_regime_state"))
        regime_bar_counts[regime] = regime_bar_counts.get(regime, 0) + 1

        for event in latest_payload.get("events", []):
            event_type = str(event.get("type") or "").upper()
            if event_type not in ENTRY_EVENTS and event_type not in EXIT_EVENTS:
                continue

            key = _event_key(event)
            if key in seen:
                continue

            seen.add(key)
            events.append(dict(event))

    return (
        events,
        latest_payload or build_trend_breakout_payload(symbol, rows, timeframe=timeframe, ai_context=ai_context),
        regime_bar_counts,
    )


def replay_trading_scenario(
    symbol: str,
    ohlc: Sequence[Mapping[str, Any]] | None,
    *,
    timeframe: str = "5m",
    ai_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    rows, dropped = _normalize_ohlc_rows(ohlc)
    events, payload, regime_bar_counts = _collect_replay_events(symbol, rows, timeframe=timeframe, ai_context=ai_context)
    trades = _simulate_trades(events, rows)
    metrics = _summarize_trades(trades, bars_count=len(rows), regime_bar_counts=regime_bar_counts)

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
        "metrics": metrics,
        "regime_bar_counts": regime_bar_counts,
        "regime_metrics": _summarize_trades_by_entry_regime(trades, regime_bar_counts=regime_bar_counts),
        "overtrading": metrics["overtrading"],
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


def analyze_forward_replays(results: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    symbol_summaries: Dict[str, Any] = {}
    all_trades: List[Dict[str, Any]] = []
    total_bars = 0
    aggregate_regime_counts: Dict[str, int] = {}

    for raw_symbol, result in (results or {}).items():
        if not isinstance(result, Mapping):
            continue

        symbol = str(result.get("symbol") or result.get("ticker") or raw_symbol).strip()
        if not symbol:
            continue

        data_quality = result.get("data_quality") if isinstance(result.get("data_quality"), Mapping) else {}
        bars_used = max(0, _safe_int(data_quality.get("bars_used")))
        regime_counts = _normalize_regime_counts(result.get("regime_bar_counts") if isinstance(result.get("regime_bar_counts"), Mapping) else {})
        trades = []

        for trade in result.get("trades") or []:
            if not isinstance(trade, Mapping):
                continue
            enriched = dict(trade)
            enriched.setdefault("symbol", symbol)
            trades.append(enriched)

        total_bars += bars_used
        all_trades.extend(trades)

        for regime, count in regime_counts.items():
            aggregate_regime_counts[regime] = aggregate_regime_counts.get(regime, 0) + count

        symbol_metrics = _summarize_trades(trades, bars_count=bars_used, regime_bar_counts=regime_counts)
        symbol_summaries[symbol] = {
            "bars_used": bars_used,
            "trades": len(trades),
            "metrics": symbol_metrics,
            "regime_metrics": _summarize_trades_by_entry_regime(trades, regime_bar_counts=regime_counts),
            "overtrading": symbol_metrics["overtrading"],
        }

    metrics = _summarize_trades(all_trades, bars_count=total_bars, regime_bar_counts=aggregate_regime_counts)
    return {
        "symbols_tested": len(symbol_summaries),
        "bars_used": total_bars,
        "metrics": metrics,
        "regime_bar_counts": aggregate_regime_counts,
        "regime_metrics": _summarize_trades_by_entry_regime(all_trades, regime_bar_counts=aggregate_regime_counts),
        "overtrading": metrics["overtrading"],
        "symbols": symbol_summaries,
    }


def forward_test_trading_scenarios(scenarios: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    replays = backtest_trading_scenarios(scenarios)
    return {
        "type": "forward_test",
        "symbols": replays,
        "analysis": analyze_forward_replays(replays),
    }


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
