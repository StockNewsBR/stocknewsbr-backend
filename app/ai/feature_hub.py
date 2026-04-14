from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.ai.ai_accumulation import run_accumulation
from app.ai.ai_breakout_probability import run_breakout_probability
from app.ai.ai_heat_map import run_heat_map
from app.ai.ai_institutional_flow import run_institutional_flow
from app.ai.ai_liquidity_map import run_liquidity_map
from app.ai.ai_liquidity_sweep import run_liquidity_sweep
from app.ai.ai_market_regime import run_market_regime
from app.ai.ai_master_score import run_master_score
from app.ai.ai_smart_money import run_smart_money
from app.ai.ai_squeeze import run_squeeze


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def pct(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return clamp(((value - low) / (high - low)) * 100.0, 0.0, 100.0)


def get_symbol(row: Dict[str, Any]) -> str:
    return (
        row.get("ticker")
        or row.get("symbol")
        or row.get("asset")
        or row.get("code")
        or "UNKNOWN"
    )


def get_name(row: Dict[str, Any]) -> str:
    return (
        row.get("name")
        or row.get("company")
        or row.get("description")
        or get_symbol(row)
    )


def merge_market_rows(
    top_signals: Iterable[Dict[str, Any]],
    ranking: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for source in top_signals or []:
        if not isinstance(source, dict):
            continue
        key = get_symbol(source)
        if key == "UNKNOWN":
            continue
        merged[key] = dict(source)

    for source in ranking or []:
        if not isinstance(source, dict):
            continue
        key = get_symbol(source)
        if key == "UNKNOWN":
            continue
        existing = merged.get(key, {})
        merged[key] = {**source, **existing}

    return list(merged.values())


def _compute_price_features(row: Dict[str, Any]) -> Dict[str, Any]:
    price = safe_float(row.get("price", row.get("close", row.get("last", row.get("last_price")))))
    prev_close = safe_float(row.get("prev_close", row.get("previous_close", price)))
    open_price = safe_float(row.get("open", row.get("open_price", price)))
    high = safe_float(row.get("high", price))
    low = safe_float(row.get("low", price))
    vwap = safe_float(row.get("vwap", price))

    change_pct = safe_float(
        row.get(
            "change_pct",
            row.get("percent_change", ((price - prev_close) / prev_close * 100.0) if prev_close else 0.0),
        )
    )

    intraday_range = max(high - low, 0.0)
    intraday_range_pct = (intraday_range / price * 100.0) if price > 0 else 0.0

    range_position = 0.5
    if high > low:
        range_position = (price - low) / (high - low)

    above_vwap = bool(vwap > 0 and price >= vwap)
    gap_pct = ((open_price - prev_close) / prev_close * 100.0) if prev_close else 0.0

    return {
        "price": price,
        "prev_close": prev_close,
        "open": open_price,
        "high": high,
        "low": low,
        "vwap": vwap,
        "change_pct": change_pct,
        "gap_pct": gap_pct,
        "intraday_range": intraday_range,
        "intraday_range_pct": intraday_range_pct,
        "range_position": range_position,
        "above_vwap": above_vwap,
    }


def _compute_volume_features(row: Dict[str, Any]) -> Dict[str, Any]:
    volume = safe_float(row.get("volume", row.get("total_volume")))
    avg_volume = safe_float(row.get("avg_volume", row.get("average_volume")))
    rel_volume = safe_float(row.get("rel_volume", row.get("relative_volume", 0.0)))

    if rel_volume <= 0 and avg_volume > 0:
        rel_volume = volume / avg_volume if avg_volume else 0.0

    volume_score = pct(rel_volume, 0.8, 3.0)
    unusual_volume = rel_volume >= 1.5

    return {
        "volume": safe_int(volume),
        "avg_volume": safe_int(avg_volume),
        "rel_volume": rel_volume,
        "volume_score": volume_score,
        "unusual_volume": unusual_volume,
    }


def _compute_indicator_features(row: Dict[str, Any]) -> Dict[str, Any]:
    rsi = safe_float(row.get("rsi", 50.0))
    adx = safe_float(row.get("adx", 15.0))
    atr_pct = safe_float(row.get("atr_pct", row.get("atr_percent", 1.0)))
    momentum = safe_float(row.get("momentum", row.get("mom", 0.0)))
    bb_width = safe_float(row.get("bb_width", row.get("bollinger_width", 0.0)))
    kc_width = safe_float(row.get("kc_width", row.get("keltner_width", 0.0)))

    trend_strength = pct(adx, 10.0, 35.0)
    volatility_score = pct(atr_pct, 0.5, 5.5)
    momentum_score = pct(abs(momentum), 0.0, 3.0)

    squeeze_ratio = 0.0
    if bb_width > 0 and kc_width > 0:
        squeeze_ratio = bb_width / kc_width if kc_width else 0.0

    squeeze_score = 100.0 - pct(squeeze_ratio, 0.8, 1.4) if squeeze_ratio > 0 else 100.0 - volatility_score

    return {
        "rsi": rsi,
        "adx": adx,
        "atr_pct": atr_pct,
        "momentum": momentum,
        "bb_width": bb_width,
        "kc_width": kc_width,
        "trend_strength": trend_strength,
        "volatility_score": volatility_score,
        "momentum_score": momentum_score,
        "squeeze_ratio": squeeze_ratio,
        "squeeze_score": clamp(squeeze_score),
    }


def _compute_setup_features(row: Dict[str, Any]) -> Dict[str, Any]:
    price = safe_float(row.get("price", row.get("close", row.get("last", 0.0))))
    high = safe_float(row.get("high", price))
    low = safe_float(row.get("low", price))
    vwap = safe_float(row.get("vwap", price))
    adx = safe_float(row.get("adx", 15.0))
    rel_volume = safe_float(row.get("rel_volume", row.get("relative_volume", 1.0)))
    change_pct = safe_float(row.get("change_pct", row.get("percent_change", 0.0)))

    range_position = 0.5
    if high > low:
        range_position = (price - low) / (high - low)

    breakout_pressure = (
        pct(range_position, 0.55, 0.98) * 0.45
        + pct(rel_volume, 0.9, 2.5) * 0.30
        + pct(adx, 12, 30) * 0.25
    )

    accumulation_bias = (
        (100.0 - pct(abs(change_pct), 1.0, 6.0)) * 0.35
        + (100.0 if price >= vwap and vwap > 0 else 35.0) * 0.25
        + pct(rel_volume, 0.9, 2.0) * 0.25
        + pct(safe_float(row.get("rsi", 50.0)), 45, 65) * 0.15
    )

    institutional_bias = (
        pct(rel_volume, 0.8, 3.0) * 0.40
        + pct(adx, 10, 35) * 0.20
        + pct(range_position, 0.35, 0.95) * 0.20
        + pct(change_pct, -1.5, 3.5) * 0.10
        + (10.0 if vwap > 0 and price > vwap else 0.0)
    )

    liquidity_magnet = 100.0 - pct(abs(price - vwap) / price if price else 0.0, 0.0, 0.02)

    return {
        "range_position": range_position,
        "breakout_pressure": clamp(breakout_pressure),
        "accumulation_bias": clamp(accumulation_bias),
        "institutional_bias": clamp(institutional_bias),
        "liquidity_magnet": clamp(liquidity_magnet),
    }


def build_asset_features(row: Dict[str, Any]) -> Dict[str, Any]:
    base = {
        **row,
        "ticker": get_symbol(row),
        "name": get_name(row),
    }

    price_features = _compute_price_features(base)
    volume_features = _compute_volume_features({**base, **price_features})
    indicator_features = _compute_indicator_features({**base, **price_features, **volume_features})
    setup_features = _compute_setup_features(
        {**base, **price_features, **volume_features, **indicator_features}
    )

    confidence_inputs = 0
    for key in [
        "price", "volume", "rel_volume", "vwap", "rsi", "adx", "atr_pct", "change_pct"
    ]:
        if safe_float(
            {
                **price_features,
                **volume_features,
                **indicator_features,
                **setup_features,
            }.get(key)
        ) != 0:
            confidence_inputs += 1

    feature_confidence = safe_int(clamp((confidence_inputs / 8.0) * 100.0, 5.0, 100.0))

    return {
        **base,
        **price_features,
        **volume_features,
        **indicator_features,
        **setup_features,
        "feature_confidence": feature_confidence,
    }


def build_feature_hub(
    top_signals: Iterable[Dict[str, Any]],
    ranking: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows = merge_market_rows(top_signals=top_signals, ranking=ranking)
    return [build_asset_features(row) for row in rows if isinstance(row, dict)]


def build_ai_outputs_from_feature_rows(
    feature_rows: Iterable[Dict[str, Any]],
    limit: int = 20,
) -> Dict[str, List[Dict[str, Any]]]:
    safe_feature_rows = [
        row for row in feature_rows or [] if isinstance(row, dict) and row.get("ticker")
    ]
    outputs: Dict[str, List[Dict[str, Any]]] = {
        "heat_map": [],
        "breakout_probability": [],
        "institutional_flow": [],
        "smart_money": [],
        "accumulation": [],
        "volatility_squeeze": [],
        "liquidity_sweep": [],
        "liquidity_map": [],
        "market_regime": [],
        "master_score": [],
    }

    try:
        outputs["heat_map"] = run_heat_map(safe_feature_rows, limit=limit)
    except Exception:
        outputs["heat_map"] = []

    try:
        outputs["breakout_probability"] = run_breakout_probability(safe_feature_rows, limit=limit)
    except Exception:
        outputs["breakout_probability"] = []

    try:
        outputs["institutional_flow"] = run_institutional_flow(safe_feature_rows, limit=limit)
    except Exception:
        outputs["institutional_flow"] = []

    try:
        outputs["smart_money"] = run_smart_money(safe_feature_rows, limit=limit)
    except Exception:
        outputs["smart_money"] = []

    try:
        outputs["accumulation"] = run_accumulation(safe_feature_rows, limit=limit)
    except Exception:
        outputs["accumulation"] = []

    try:
        outputs["volatility_squeeze"] = run_squeeze(safe_feature_rows, limit=limit)
    except Exception:
        outputs["volatility_squeeze"] = []

    try:
        outputs["liquidity_sweep"] = run_liquidity_sweep(safe_feature_rows, limit=limit)
    except Exception:
        outputs["liquidity_sweep"] = []

    try:
        outputs["liquidity_map"] = run_liquidity_map(safe_feature_rows, limit=limit)
    except Exception:
        outputs["liquidity_map"] = []

    try:
        outputs["market_regime"] = run_market_regime(safe_feature_rows, limit=limit)
    except Exception:
        outputs["market_regime"] = []

    try:
        subscore_index: Dict[str, Dict[str, Any]] = {}

        def merge_subscores(rows: Iterable[Dict[str, Any]], field_name: str) -> None:
            for row in rows:
                ticker = row.get("ticker")
                if not ticker:
                    continue
                entry = subscore_index.setdefault(str(ticker), {})
                entry[field_name] = row.get("score", 0)

        merge_subscores(outputs["heat_map"], "heat_map_score")
        merge_subscores(outputs["breakout_probability"], "breakout_probability_score")
        merge_subscores(outputs["institutional_flow"], "institutional_flow_score")
        merge_subscores(outputs["smart_money"], "smart_money_score")
        merge_subscores(outputs["accumulation"], "accumulation_score")
        merge_subscores(outputs["volatility_squeeze"], "volatility_squeeze_score")
        merge_subscores(outputs["liquidity_sweep"], "liquidity_sweep_score")
        merge_subscores(outputs["liquidity_map"], "liquidity_map_score")
        merge_subscores(outputs["market_regime"], "market_regime_score")

        master_input: List[Dict[str, Any]] = []
        for row in safe_feature_rows:
            ticker = row.get("ticker")
            if not ticker:
                continue
            merged = dict(row)
            merged.update(subscore_index.get(str(ticker), {}))
            master_input.append(merged)

        outputs["master_score"] = run_master_score(master_input, limit=limit)
    except Exception:
        outputs["master_score"] = []

    return outputs


def build_ai_tool_payload(
    top_signals: Iterable[Dict[str, Any]],
    ranking: Iterable[Dict[str, Any]],
    limit: int = 20,
) -> Dict[str, List[Dict[str, Any]]]:
    return build_ai_outputs_from_feature_rows(
        build_feature_hub(top_signals=top_signals, ranking=ranking),
        limit=limit,
    )
