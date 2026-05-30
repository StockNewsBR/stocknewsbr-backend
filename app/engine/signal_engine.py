from __future__ import annotations

from typing import Any, Dict

from app.ai.ai_market_regime import run_market_regime
from app.ai.ai_master_score import run_master_score
from app.ai.ai_smart_money import run_smart_money
from app.ai.feature_hub import build_asset_features
from app.cache.snapshot_cache import get_snapshot, get_snapshot_by_ticker
from app.engine.trend_breakout_signal_engine import build_trend_breakout_payload, resolve_chart_timeframe
from app.market.market_data_loader import get_ticker_frame


def _normalize_symbol(value: str | None) -> str:
    return str(value or "").upper().strip().replace(".SA", "").replace("-USD", "USD")


def _find_ai_row(tool_rows, symbol: str):
    normalized = _normalize_symbol(symbol)

    for row in tool_rows or []:
        if not isinstance(row, dict):
            continue

        row_symbol = _normalize_symbol(row.get("ticker") or row.get("symbol"))

        if row_symbol == normalized:
            return dict(row)

    return None


def _build_ai_context_from_snapshot(symbol: str) -> Dict[str, Any]:
    snapshot = get_snapshot()
    ai_tools = snapshot.get("ai_tools", {}) if isinstance(snapshot, dict) else {}
    by_ticker = get_snapshot_by_ticker()
    normalized = _normalize_symbol(symbol)

    context = {
        "heat_map": _find_ai_row(ai_tools.get("heat_map", []), normalized),
        "breakout_probability": _find_ai_row(ai_tools.get("breakout_probability", []), normalized),
        "institutional_flow": _find_ai_row(ai_tools.get("institutional_flow", []), normalized),
        "smart_money": _find_ai_row(ai_tools.get("smart_money", []), normalized),
        "accumulation": _find_ai_row(ai_tools.get("accumulation", []), normalized),
        "volatility_squeeze": _find_ai_row(ai_tools.get("volatility_squeeze", []), normalized),
        "liquidity_sweep": _find_ai_row(ai_tools.get("liquidity_sweep", []), normalized),
        "liquidity_map": _find_ai_row(ai_tools.get("liquidity_map", []), normalized),
        "market_regime": _find_ai_row(ai_tools.get("market_regime", []), normalized),
        "master_score": _find_ai_row(ai_tools.get("master_score", []), normalized),
    }

    if context["market_regime"] and context["smart_money"] and context["master_score"]:
        return context

    seed_row = by_ticker.get(normalized)

    if not isinstance(seed_row, dict):
        return context

    feature_row = build_asset_features(seed_row)
    fallback_regime = run_market_regime([feature_row], limit=1)
    fallback_smart_money = run_smart_money([feature_row], limit=1)

    master_input = dict(feature_row)

    if fallback_regime:
        master_input["market_regime_score"] = fallback_regime[0].get("score", 0)

    if fallback_smart_money:
        master_input["smart_money_score"] = fallback_smart_money[0].get("score", 0)

    fallback_master_score = run_master_score([master_input], limit=1)

    return {
        **context,
        "market_regime": context["market_regime"] or (fallback_regime[0] if fallback_regime else None),
        "smart_money": context["smart_money"] or (fallback_smart_money[0] if fallback_smart_money else None),
        "master_score": context["master_score"] or (fallback_master_score[0] if fallback_master_score else None),
    }


def _frame_to_ohlc(frame):
    rows = []

    if frame is None or frame.empty:
        return rows

    for index, row in frame.tail(240).iterrows():
        rows.append(
            {
                "time": str(index),
                "open": float(row.get("Open", 0) or 0),
                "high": float(row.get("High", 0) or 0),
                "low": float(row.get("Low", 0) or 0),
                "close": float(row.get("Close", 0) or 0),
                "volume": float(row.get("Volume", 0) or 0),
            }
        )

    return rows


def generate_signal_payload(
    symbol: str,
    period: str = "1mo",
    interval: str = "5m",
):
    frame = get_ticker_frame(symbol, period=period, interval=interval)

    if frame is None or frame.empty:
        return None

    ohlc = _frame_to_ohlc(frame)
    return build_chart_signal_payload(symbol, ohlc, interval=interval)


def build_chart_signal_payload(symbol: str, ohlc, interval: str = "1D"):
    ai_context = _build_ai_context_from_snapshot(symbol)
    return build_trend_breakout_payload(
        symbol,
        ohlc,
        timeframe=resolve_chart_timeframe(interval),
        ai_context=ai_context,
    )


def generate_signals(symbol: str):
    payload = generate_signal_payload(symbol, period="1mo", interval="5m")

    if not payload:
        return []

    return payload.get("events", [])
