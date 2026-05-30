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
from app.ai.ai_radar import run_radar
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
    symbol = get_symbol(row)
    return (
        row.get("name")
        or row.get("company")
        or row.get("description")
        or _fallback_name(symbol)
    )


def _fallback_name(symbol: str) -> str:
    normalized = str(symbol or "").upper().strip()
    if not normalized:
        return "UNKNOWN"
    if normalized.endswith(".SA"):
        base = normalized[:-3]
        return f"{base} BDR" if base.endswith("34") else base
    if normalized.endswith("-USD"):
        return normalized.replace("-USD", " Crypto")
    if normalized.isalpha() and len(normalized) <= 6:
        return f"{normalized} US"
    return normalized


def _normalize_source_score(row: Dict[str, Any]) -> float:
    value = safe_float(row.get("score", row.get("signal_score", row.get("ranking_score", 0.0))))
    if 0.0 < value <= 10.0:
        value *= 10.0
    return clamp(value)


def _symbol_factor(symbol: str) -> float:
    normalized = str(symbol or "UNKNOWN").upper().strip()
    raw = sum((index + 1) * ord(char) for index, char in enumerate(normalized))
    return (raw % 1000) / 10.0


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
        existing = merged.get(key)
        if not existing or _normalize_source_score(source) >= _normalize_source_score(existing):
            merged[key] = {**(existing or {}), **source}

    for source in ranking or []:
        if not isinstance(source, dict):
            continue
        key = get_symbol(source)
        if key == "UNKNOWN":
            continue
        existing = merged.get(key, {})
        if not existing or _normalize_source_score(source) >= _normalize_source_score(existing):
            merged[key] = {**existing, **source}
        else:
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
    source_score = safe_float(row.get("source_score", 0.0))
    symbol_factor = safe_float(row.get("symbol_factor", 50.0))
    has_volatility_input = any(
        row.get(key) not in (None, "")
        for key in ("atr_pct", "atr_percent", "bb_width", "bollinger_width", "kc_width", "keltner_width")
    )

    trend_strength = pct(adx, 10.0, 35.0)
    volatility_score = pct(atr_pct, 0.5, 5.5)
    momentum_score = pct(abs(momentum), 0.0, 3.0)

    squeeze_ratio = 0.0
    if bb_width > 0 and kc_width > 0:
        squeeze_ratio = bb_width / kc_width if kc_width else 0.0

    if squeeze_ratio > 0:
        squeeze_score = 100.0 - pct(squeeze_ratio, 0.8, 1.4)
    elif has_volatility_input:
        squeeze_score = 100.0 - volatility_score
    else:
        squeeze_score = 35.0 + source_score * 0.28 + symbol_factor * 0.06

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
    source_score = safe_float(row.get("source_score", 0.0))
    symbol_factor = safe_float(row.get("symbol_factor", 50.0))
    has_price = price > 0

    range_position = 0.25 + (symbol_factor / 100.0) * 0.5 if not has_price else 0.5
    if high > low:
        range_position = (price - low) / (high - low)

    distance_to_resistance_pct = ((high - price) / price * 100.0) if price > 0 else 0.0
    distance_to_support_pct = ((price - low) / price * 100.0) if price > 0 else 0.0
    stability_score = 100.0 - pct(abs(change_pct), 0.4, 4.0)
    if not has_price:
        stability_score = clamp(45.0 + (100.0 - abs(source_score - 50.0)) * 0.28 + symbol_factor * 0.08)
    absorption_score = (
        pct(rel_volume, 0.9, 2.4) * 0.35
        + (100.0 - pct(abs(change_pct), 0.5, 4.5)) * 0.30
        + (100.0 if vwap > 0 and price >= vwap else 35.0) * 0.20
        + pct(adx, 10, 28) * 0.15
    )
    flow_persistence = (
        pct(adx, 12, 35) * 0.35
        + pct(abs(change_pct), 0.1, 3.0) * 0.20
        + pct(rel_volume, 1.0, 3.0) * 0.25
        + (20.0 if vwap > 0 and price >= vwap else 8.0)
    )
    large_flow_score = pct(rel_volume, 1.0, 4.0) * 0.70 + pct(safe_float(row.get("volume")), 0.0, 5_000_000.0) * 0.30
    discrete_buying_score = stability_score * 0.45 + absorption_score * 0.35 + pct(rel_volume, 0.8, 1.8) * 0.20
    defended_level = "vwap" if vwap > 0 and price >= vwap else "support" if range_position <= 0.35 else "resistance" if range_position >= 0.75 else "range_mid"

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
    false_breakout_risk = (
        pct(range_position, 0.70, 1.0) * 0.25
        + pct(distance_to_resistance_pct, 0.0, 1.5) * 0.20
        + (100.0 - pct(rel_volume, 0.8, 2.0)) * 0.30
        + pct(abs(change_pct), 1.5, 5.0) * 0.25
    )

    if not has_price:
        breakout_pressure = clamp(source_score * 0.34 + range_position * 24.0 + symbol_factor * 0.08)
        accumulation_bias = clamp((100.0 - abs(source_score - 50.0)) * 0.28 + source_score * 0.18 + symbol_factor * 0.08)
        institutional_bias = clamp(source_score * 0.24 + symbol_factor * 0.08)
        liquidity_magnet = clamp(25.0 + source_score * 0.20 + (100.0 - symbol_factor) * 0.05)
        false_breakout_risk = clamp((100.0 - source_score) * 0.24 + symbol_factor * 0.10)
        absorption_score = clamp(35.0 + source_score * 0.18 + symbol_factor * 0.06)
        flow_persistence = clamp(20.0 + source_score * 0.22 + symbol_factor * 0.05)
        large_flow_score = clamp(source_score * 0.18 + symbol_factor * 0.04)
        discrete_buying_score = clamp(stability_score * 0.45 + absorption_score * 0.35 + source_score * 0.20)

    return {
        "range_position": range_position,
        "breakout_pressure": clamp(breakout_pressure),
        "accumulation_bias": clamp(accumulation_bias),
        "institutional_bias": clamp(institutional_bias),
        "liquidity_magnet": clamp(liquidity_magnet),
        "resistance": high,
        "support": low,
        "distance_to_resistance_pct": max(0.0, distance_to_resistance_pct),
        "distance_to_support_pct": max(0.0, distance_to_support_pct),
        "stability_score": clamp(stability_score),
        "absorption_score": clamp(absorption_score),
        "flow_persistence": clamp(flow_persistence),
        "large_flow_score": clamp(large_flow_score),
        "discrete_buying_score": clamp(discrete_buying_score),
        "defended_level": defended_level,
        "false_breakout_risk": clamp(false_breakout_risk),
    }


def build_asset_features(row: Dict[str, Any]) -> Dict[str, Any]:
    symbol = get_symbol(row)
    base = {
        **row,
        "ticker": symbol,
        "name": get_name(row),
        "source_score": _normalize_source_score(row),
        "symbol_factor": _symbol_factor(symbol),
    }

    price_features = _compute_price_features(base)
    volume_features = _compute_volume_features({**base, **price_features})
    indicator_features = _compute_indicator_features({**base, **price_features, **volume_features})
    setup_features = _compute_setup_features(
        {**base, **price_features, **volume_features, **indicator_features}
    )

    confidence_inputs = 0
    for key in [
        "price", "volume", "rel_volume", "vwap", "rsi", "adx", "atr_pct", "change_pct", "source_score"
    ]:
        if safe_float(
            {
                **base,
                **price_features,
                **volume_features,
                **indicator_features,
                **setup_features,
            }.get(key)
        ) != 0:
            confidence_inputs += 1

    feature_confidence = safe_int(clamp((confidence_inputs / 9.0) * 100.0, 5.0, 100.0))

    return {
        **base,
        **price_features,
        **volume_features,
        **indicator_features,
        **setup_features,
        "data_quality": "priced" if price_features.get("price", 0) > 0 else "score_only",
        "feature_confidence": feature_confidence,
    }


def build_feature_hub(
    top_signals: Iterable[Dict[str, Any]],
    ranking: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows = merge_market_rows(top_signals=top_signals, ranking=ranking)
    features = [build_asset_features(row) for row in rows if isinstance(row, dict)]
    return _add_cross_section_features(features)


def _rank_pct(value: float, values: List[float]) -> float:
    if not values:
        return 50.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return 50.0
    if ordered[0] == ordered[-1]:
        return 50.0
    below_or_equal = sum(1 for item in ordered if item <= value)
    return clamp(((below_or_equal - 1) / (len(ordered) - 1)) * 100.0)


def _add_cross_section_features(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    changes = [safe_float(row.get("change_pct")) for row in rows]
    momentums = [safe_float(row.get("momentum")) for row in rows]
    rel_volumes = [safe_float(row.get("rel_volume")) for row in rows]
    source_scores = [safe_float(row.get("source_score")) for row in rows]

    enriched: List[Dict[str, Any]] = []
    for row in rows:
        change = safe_float(row.get("change_pct"))
        momentum = safe_float(row.get("momentum"))
        rel_volume = safe_float(row.get("rel_volume"))
        source_score = safe_float(row.get("source_score"))
        source_rank = _rank_pct(source_score, source_scores)
        relative_strength = (
            _rank_pct(change, changes) * 0.30
            + _rank_pct(momentum, momentums) * 0.22
            + _rank_pct(rel_volume, rel_volumes) * 0.20
            + source_rank * 0.28
        )
        enriched.append(
            {
                **row,
                "relative_strength_score": round(clamp(relative_strength), 4),
                "relative_weakness_score": round(clamp(100.0 - relative_strength), 4),
                "source_score_rank": round(source_rank, 4),
                "market_relative_change": round(change - (sum(changes) / max(1, len(changes))), 4),
                "abnormal_move_score": round(
                    clamp(
                        abs(change) * 14.0
                        + abs(momentum) * 10.0
                        + max(rel_volume - 1.0, 0.0) * 24.0
                        + abs(source_score - 50.0) * 0.20
                    ),
                    4,
                ),
            }
        )
    return enriched


def build_ai_outputs_from_feature_rows(
    feature_rows: Iterable[Dict[str, Any]],
    limit: int = 20,
) -> Dict[str, List[Dict[str, Any]]]:
    safe_feature_rows = [
        row for row in feature_rows or [] if isinstance(row, dict) and row.get("ticker")
    ]
    outputs: Dict[str, List[Dict[str, Any]]] = {
        "heat_map": [],
        "radar": [],
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
        outputs["radar"] = run_radar(safe_feature_rows, limit=limit)
    except Exception:
        outputs["radar"] = []

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

        def merge_subscores(rows: Iterable[Dict[str, Any]], field_name: str, state_field: str | None = None) -> None:
            for row in rows:
                ticker = row.get("ticker")
                if not ticker:
                    continue
                entry = subscore_index.setdefault(str(ticker), {})
                entry[field_name] = row.get("score", 0)
                if state_field:
                    entry[state_field] = row.get("state")

        merge_subscores(outputs["heat_map"], "heat_map_score", "heat_map_state")
        merge_subscores(outputs["radar"], "radar_score", "radar_state")
        merge_subscores(outputs["breakout_probability"], "breakout_probability_score", "breakout_probability_state")
        merge_subscores(outputs["institutional_flow"], "institutional_flow_score", "institutional_flow_state")
        merge_subscores(outputs["smart_money"], "smart_money_score", "smart_money_state")
        merge_subscores(outputs["accumulation"], "accumulation_score", "accumulation_state")
        merge_subscores(outputs["volatility_squeeze"], "volatility_squeeze_score", "volatility_squeeze_state")
        merge_subscores(outputs["liquidity_sweep"], "liquidity_sweep_score", "liquidity_sweep_state")
        merge_subscores(outputs["liquidity_map"], "liquidity_map_score", "liquidity_map_state")
        merge_subscores(outputs["market_regime"], "market_regime_score", "market_regime_state")

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
