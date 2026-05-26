from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.ai.trade_decision import evaluate_trade_coherence
from app.market.market_universe import B3_CORE, B3_EXTENDED, BDRS, CRYPTO

logger = logging.getLogger("stocknewsbr.trend_breakout_signal_engine")
_PANDAS = None

_CHART_INTERVAL_TO_TIMEFRAME = {
    "1D": "5m",
    "1W": "30m",
    "1M": "1d",
    "3M": "1d",
    "6M": "1d",
    "YTD": "1d",
    "1Y": "1d",
    "ALL": "1wk",
}

_INTRADAY_TIMEFRAMES = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}

_PROFILE_DEFAULTS = {
    "b3_stock": {
        "breakout_lookback": 12,
        "atr_period": 14,
        "slope_lookback": 3,
        "volume_lookback": 20,
        "volume_factor": 1.04,
        "atr_pct_min": 0.0016,
        "atr_pct_max": 0.0850,
        "body_atr_min": 0.30,
        "spread_atr_min": 0.10,
        "buffer_atr_mult": 0.06,
        "ema_distance_atr": 2.40,
        "max_range_atr_mult": 2.25,
        "max_body_atr_mult": 1.65,
        "score_min": 7,
        "pullback_max_bars": 4,
        "max_hold_bars": 8,
        "cooldown_bars_after_exit": 2,
        "resistance_room_atr": 0.42,
        "support_room_atr": 0.42,
        "wick_max_ratio": 0.38,
        "reject_wick_min_ratio": 0.12,
        "min_score_edge": 1,
    },
    "bdr": {
        "breakout_lookback": 12,
        "atr_period": 14,
        "slope_lookback": 3,
        "volume_lookback": 20,
        "volume_factor": 1.08,
        "atr_pct_min": 0.0018,
        "atr_pct_max": 0.0750,
        "body_atr_min": 0.34,
        "spread_atr_min": 0.11,
        "buffer_atr_mult": 0.07,
        "ema_distance_atr": 2.15,
        "max_range_atr_mult": 2.05,
        "max_body_atr_mult": 1.50,
        "score_min": 8,
        "pullback_max_bars": 3,
        "max_hold_bars": 7,
        "cooldown_bars_after_exit": 2,
        "resistance_room_atr": 0.48,
        "support_room_atr": 0.48,
        "wick_max_ratio": 0.34,
        "reject_wick_min_ratio": 0.14,
        "min_score_edge": 2,
    },
    "us_stock": {
        "breakout_lookback": 12,
        "atr_period": 14,
        "slope_lookback": 3,
        "volume_lookback": 20,
        "volume_factor": 1.01,
        "atr_pct_min": 0.0010,
        "atr_pct_max": 0.0900,
        "body_atr_min": 0.26,
        "spread_atr_min": 0.09,
        "buffer_atr_mult": 0.05,
        "ema_distance_atr": 3.00,
        "max_range_atr_mult": 2.50,
        "max_body_atr_mult": 1.80,
        "score_min": 6,
        "pullback_max_bars": 4,
        "max_hold_bars": 10,
        "cooldown_bars_after_exit": 2,
        "resistance_room_atr": 0.38,
        "support_room_atr": 0.38,
        "wick_max_ratio": 0.42,
        "reject_wick_min_ratio": 0.10,
        "min_score_edge": 1,
    },
    "crypto": {
        "breakout_lookback": 10,
        "atr_period": 14,
        "slope_lookback": 3,
        "volume_lookback": 20,
        "volume_factor": 0.98,
        "atr_pct_min": 0.0030,
        "atr_pct_max": 0.1800,
        "body_atr_min": 0.32,
        "spread_atr_min": 0.10,
        "buffer_atr_mult": 0.08,
        "ema_distance_atr": 3.35,
        "max_range_atr_mult": 3.20,
        "max_body_atr_mult": 2.20,
        "score_min": 6,
        "pullback_max_bars": 5,
        "max_hold_bars": 12,
        "cooldown_bars_after_exit": 2,
        "resistance_room_atr": 0.55,
        "support_room_atr": 0.55,
        "wick_max_ratio": 0.46,
        "reject_wick_min_ratio": 0.08,
        "min_score_edge": 1,
    },
}


def _get_pandas():
    global _PANDAS
    if _PANDAS is None:
        import pandas as pd_module

        _PANDAS = pd_module
    return _PANDAS

_B3_UNIVERSE = {str(ticker).upper().strip() for ticker in (*B3_CORE, *B3_EXTENDED)}
_BDR_UNIVERSE = {str(ticker).upper().strip() for ticker in BDRS}
_CRYPTO_UNIVERSE = {str(ticker).upper().strip() for ticker in CRYPTO}
_B3_DISPLAY_UNIVERSE = {ticker.replace(".SA", "") for ticker in _B3_UNIVERSE}
_BDR_DISPLAY_UNIVERSE = {ticker.replace(".SA", "") for ticker in _BDR_UNIVERSE}
_CRYPTO_DISPLAY_UNIVERSE = {ticker.replace("-USD", "USD") for ticker in _CRYPTO_UNIVERSE}

_PROFILE_AI_RULES = {
    "b3_stock": {
        "bear_block_master_score": 70,
        "bull_block_master_score": 70,
        "high_vol_block_master_score": 60,
        "low_score_floor": 45,
    },
    "bdr": {
        "bear_block_master_score": 75,
        "bull_block_master_score": 75,
        "high_vol_block_master_score": 65,
        "low_score_floor": 48,
    },
    "us_stock": {
        "bear_block_master_score": 68,
        "bull_block_master_score": 68,
        "high_vol_block_master_score": 58,
        "low_score_floor": 42,
    },
    "crypto": {
        "bear_block_master_score": 62,
        "bull_block_master_score": 62,
        "high_vol_block_master_score": 52,
        "low_score_floor": 40,
    },
}


def _ai_score(row: Dict[str, Any] | None, default: float = 50.0) -> float:
    if not isinstance(row, dict):
        return default
    try:
        value = row.get("score")
        return default if value is None else float(value)
    except Exception:
        return default


def _ai_state(row: Dict[str, Any] | None) -> str:
    return str((row or {}).get("state") or "").strip().lower()


def _coherence_context_row(
    *,
    display: str,
    ai_bias: Dict[str, Any],
    close: float,
    ema_mid: float,
    volume_rel: float,
    volume_known: bool,
    trend_strength: float,
    score_long: float,
    score_short: float,
    breakout_state: str,
    chart_regime_state: str,
    liquidity_event: str,
) -> Dict[str, Any]:
    return {
        "ticker": display,
        "market_regime_state": ai_bias.get("market_regime_state"),
        "chart_regime_state": chart_regime_state,
        "market_structure_state": chart_regime_state,
        "liquidity_event": liquidity_event,
        "market_regime_score": ai_bias.get("market_regime_score"),
        "smart_money_state": ai_bias.get("smart_money_state"),
        "smart_money_score": ai_bias.get("smart_money_score"),
        "institutional_flow_state": ai_bias.get("institutional_flow_state"),
        "institutional_flow_score": ai_bias.get("institutional_flow_score"),
        "breakout_probability_state": breakout_state or ai_bias.get("breakout_probability_state"),
        "breakout_probability_score": ai_bias.get("breakout_probability_score"),
        "volatility_squeeze_state": ai_bias.get("volatility_squeeze_state"),
        "liquidity_sweep_state": ai_bias.get("liquidity_sweep_state"),
        "liquidity_map_state": ai_bias.get("liquidity_map_state"),
        "heat_map_score": ai_bias.get("heat_map_score"),
        "master_score": ai_bias.get("master_score"),
        "above_vwap": close >= ema_mid if ema_mid > 0 else False,
        "rel_volume": volume_rel,
        "volume_known": bool(volume_known),
        "volume_score": max(0.0, min(100.0, (volume_rel - 0.8) / 1.4 * 100.0)),
        "trend_strength": trend_strength,
        "bullish_pressure": score_long,
        "bearish_pressure": score_short,
        "data_quality": "priced",
    }


_EVENT_COPY = {
    "BUY": {
        "label": "Buy Long",
        "direction": "abrir long",
        "note": "Entrada long",
        "confirmation": "Confirmar rompimento/pullback com volume, VWAP/EMA21 e fluxo no mesmo lado.",
    },
    "SELL": {
        "label": "Close Long",
        "direction": "encerrar long",
        "note": "Saida long",
        "confirmation": "Encerrar se perder VWAP/EMA21, regime virar ou aparecer sinal vendedor confirmado.",
    },
    "SHORT": {
        "label": "Sell Short",
        "direction": "abrir short",
        "note": "Entrada short",
        "confirmation": "Confirmar perda de suporte/VWAP com volume e pressao vendedora persistente.",
    },
    "COVER": {
        "label": "Close Short",
        "direction": "encerrar short",
        "note": "Saida short",
        "confirmation": "Encerrar se recuperar VWAP/EMA21, regime virar ou aparecer compra institucional.",
    },
}


_REASON_COPY = {
    "breakout": "Rompimento confirmado por tendencia, expansao de candle e volume.",
    "resistance_reclaim": "Rompimento/retomada de resistencia com preco aceito acima da zona e estrutura virando a favor.",
    "support_reject": "Falha/rejeicao de suporte com preco aceito abaixo da zona e pressao vendedora dominante.",
    "pullback_resume": "Retomada apos pullback com defesa de media/VWAP e volume voltando.",
    "trend_continuation": "Continuacao de tendencia com estrutura, volume e pressao no mesmo lado.",
    "trend_acceptance": "Tendencia aceita pelo preco do lado operacional da VWAP/media com pressao suficiente para entrada.",
    "liquidity_reversal": "Reacao em zona de liquidez com defesa/rejeicao e fluxo voltando a favor.",
    "trend_loss": "Perda da estrutura usada na entrada.",
    "ai_regime_flip": "IA/regime virou contra a posicao.",
    "opposite_signal": "Sinal oposto confirmado com score suficiente.",
    "protect_profit": "Protecao de ganho apos deslocamento favoravel.",
    "micro_structure_loss": "Perda curta de estrutura antes de virar prejuizo operacional.",
    "session_close": "Fechamento operacional no final do dia para nao carregar posicao overnight.",
}


def _event_copy(event_type: str, reason: str | None, coherence: Dict[str, Any]) -> Dict[str, Any]:
    event_key = str(event_type or "").upper()
    base = _EVENT_COPY.get(event_key, {"label": event_key or "Watch", "direction": "observar", "note": "Observar", "confirmation": ""})
    reason_key = str(reason or "").strip()
    reason_text = _REASON_COPY.get(reason_key, reason_key or "Evento tecnico do grafico.")
    trigger = coherence.get("trigger") or base.get("confirmation")
    invalidation = coherence.get("invalidation") or "Invalidar se preco, volume, regime ou fluxo negarem a tese."
    risk = coherence.get("risk") or "Risco operacional depende de confirmacao de volume, tendencia e liquidez."

    return {
        "label": base["label"],
        "direction": base["direction"],
        "note": base["note"],
        "reason_text": reason_text,
        "confirmation": base.get("confirmation") or trigger,
        "trigger": trigger,
        "invalidation": invalidation,
        "risk": risk,
    }


def _event_payload(
    *,
    event_type: str,
    price: float,
    time_value: Any,
    score: float,
    reason: str,
    coherence: Dict[str, Any],
    confidence: float | None = None,
    chart_regime_state: str | None = None,
    liquidity_event: str | None = None,
) -> Dict[str, Any]:
    copy = _event_copy(event_type, reason, coherence)
    return {
        "type": event_type,
        "price": round(price, 4),
        "time": time_value,
        "score": score,
        "confidence": round(float(confidence), 1) if confidence is not None else None,
        "reason": reason,
        "reason_text": copy["reason_text"],
        "strategy": "trend_breakout_v1",
        "label": copy["label"],
        "action_label": copy["label"],
        "operational_note": copy["note"],
        "direction": copy["direction"],
        "confirmation": copy["confirmation"],
        "trigger": copy["trigger"],
        "invalidation": copy["invalidation"],
        "risk": copy["risk"],
        "risk_level": coherence.get("risk_level"),
        "coherence_status": coherence.get("coherence_status"),
        "chart_regime_state": chart_regime_state,
        "liquidity_event": liquidity_event,
        "blocked_reasons": coherence.get("blocked_reasons", []),
        "warnings": coherence.get("warnings", []),
    }


def _build_ai_bias(ai_context: Dict[str, Any] | None, profile: str) -> Dict[str, Any]:
    context = ai_context or {}
    heat_map = context.get("heat_map")
    breakout_probability = context.get("breakout_probability")
    institutional_flow = context.get("institutional_flow")
    market_regime = context.get("market_regime")
    smart_money = context.get("smart_money")
    volatility_squeeze = context.get("volatility_squeeze")
    liquidity_sweep = context.get("liquidity_sweep")
    liquidity_map = context.get("liquidity_map")
    master_score = context.get("master_score")
    profile_rules = _PROFILE_AI_RULES.get(profile, _PROFILE_AI_RULES["us_stock"])

    regime_state = _ai_state(market_regime)
    regime_score = _ai_score(market_regime)
    heat_map_score = _ai_score(heat_map)
    breakout_score = _ai_score(breakout_probability)
    flow_score = _ai_score(institutional_flow)
    smart_money_score = _ai_score(smart_money)
    volatility_squeeze_state = _ai_state(volatility_squeeze)
    master_score_value = _ai_score(master_score)

    long_bonus = 0
    short_bonus = 0
    long_block = False
    short_block = False
    threshold_adjust = 0

    regime_is_bull = regime_state in {"bull_trend", "bullish", "uptrend"}
    regime_is_bear = regime_state in {"bear_trend", "bearish", "downtrend"}
    regime_is_high_vol = regime_state == "high_volatility"
    regime_is_range = regime_state in {"range", "sideways", "neutral"}

    if regime_is_bull:
        long_bonus += 3
        short_bonus -= 3
    elif regime_is_bear:
        short_bonus += 3
        long_bonus -= 3
    elif regime_is_high_vol:
        long_bonus -= 1
        short_bonus -= 1
        threshold_adjust += 1
    elif regime_is_range:
        threshold_adjust += 1

    if smart_money_score >= 75:
        long_bonus += 2
        short_bonus -= 1
    elif smart_money_score >= 60:
        long_bonus += 1
    elif smart_money_score <= 25:
        short_bonus += 1
        long_bonus -= 1

    if flow_score >= 75:
        long_bonus += 2
        short_bonus -= 1
    elif flow_score <= 25:
        short_bonus += 2
        long_bonus -= 1

    if breakout_score >= 75:
        long_bonus += 1
        short_bonus += 1

    if volatility_squeeze_state in {"squeeze_ready", "compression"} and smart_money_score >= 60 and not regime_is_bear:
        long_bonus += 2
        short_block = True

    if master_score_value >= 85:
        if regime_is_bull:
            long_bonus += 2
            threshold_adjust -= 1
        elif regime_is_bear:
            short_bonus += 2
            threshold_adjust -= 1
        else:
            long_bonus += 1
            short_bonus += 1
    elif master_score_value >= 70:
        if regime_is_bull:
            long_bonus += 1
        elif regime_is_bear:
            short_bonus += 1
    elif 0 < master_score_value < profile_rules["low_score_floor"]:
        threshold_adjust += 2
        if regime_is_bull:
            long_bonus -= 2
        elif regime_is_bear:
            short_bonus -= 2
        else:
            long_bonus -= 1
            short_bonus -= 1

    if regime_is_bear and master_score_value < profile_rules["bear_block_master_score"]:
        long_block = True
    if regime_is_bull and master_score_value < profile_rules["bull_block_master_score"]:
        short_block = True

    if regime_is_high_vol and master_score_value < profile_rules["high_vol_block_master_score"]:
        long_block = True
        short_block = True

    exit_long_on_ai = regime_is_bear and (master_score_value < 60 or smart_money_score < 45)
    exit_short_on_ai = regime_is_bull and (master_score_value < 60 or smart_money_score >= 60)

    return {
        "market_regime_state": regime_state,
        "market_regime_score": regime_score,
        "heat_map_score": heat_map_score,
        "breakout_probability_state": _ai_state(breakout_probability),
        "breakout_probability_score": breakout_score,
        "institutional_flow_state": _ai_state(institutional_flow),
        "institutional_flow_score": flow_score,
        "smart_money_state": _ai_state(smart_money),
        "smart_money_score": smart_money_score,
        "volatility_squeeze_state": volatility_squeeze_state,
        "liquidity_sweep_state": _ai_state(liquidity_sweep),
        "liquidity_map_state": _ai_state(liquidity_map),
        "master_score": master_score_value,
        "long_bonus": long_bonus,
        "short_bonus": short_bonus,
        "long_block": long_block,
        "short_block": short_block,
        "threshold_adjust": threshold_adjust,
        "exit_long_on_ai": exit_long_on_ai,
        "exit_short_on_ai": exit_short_on_ai,
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return default


def _classify_chart_regime(
    *,
    long_trend: bool,
    short_trend: bool,
    long_breakout: bool,
    short_breakout: bool,
    spread_atr: float,
    body_atr: float,
    volume_rel: float,
    vol_rel_day: float,
    volatility_ok: bool,
) -> str:
    if long_breakout:
        return "breakout_up"
    if short_breakout:
        return "breakout_down"
    if long_trend and volatility_ok and spread_atr >= 0.14:
        return "trend_up"
    if short_trend and volatility_ok and spread_atr >= 0.14:
        return "trend_down"
    if vol_rel_day < 0.78 and body_atr < 0.25:
        return "squeeze"
    if spread_atr < 0.10 and volume_rel < 1.12:
        return "chop"
    return "range"


def _detect_liquidity_event(
    *,
    open_price: float,
    close: float,
    high: float,
    low: float,
    resistance: float,
    support: float,
    buffer: float,
    body: float,
    upper_wick: float,
    lower_wick: float,
    body_atr: float,
    volume_rel: float,
) -> str:
    wick_base = max(body, abs(close) * 0.0001)
    if resistance > 0 and high > (resistance + buffer) and close < resistance and upper_wick >= wick_base * 0.55:
        return "sweep_high_reject"
    if support > 0 and low < (support - buffer) and close > support and lower_wick >= wick_base * 0.55:
        return "sweep_low_reclaim"
    if volume_rel >= 1.25 and body_atr <= 0.30:
        if resistance > 0 and high >= (resistance - buffer) and close <= open_price:
            return "supply_absorption"
        if support > 0 and low <= (support + buffer) and close >= open_price:
            return "demand_absorption"
    return "none"


def _setup_confidence(
    *,
    side: str,
    score_side: float,
    score_opposite: float,
    required_score: float,
    trend_strength: float,
    volume_rel: float,
    chart_regime_state: str,
    liquidity_event: str,
) -> float:
    confidence = 48.0 + max(-12.0, min(18.0, (score_side - required_score) * 4.0))
    confidence += max(-10.0, min(16.0, (score_side - score_opposite) * 2.5))
    confidence += max(0.0, min(12.0, (trend_strength - 35.0) * 0.25))
    confidence += max(0.0, min(8.0, (volume_rel - 1.0) * 8.0))

    if side == "long":
        if chart_regime_state in {"trend_up", "breakout_up", "reversal_up"}:
            confidence += 8.0
        if liquidity_event in {"sweep_low_reclaim", "demand_absorption"}:
            confidence += 6.0
        if liquidity_event in {"sweep_high_reject", "supply_absorption"}:
            confidence -= 12.0
    else:
        if chart_regime_state in {"trend_down", "breakout_down", "reversal_down"}:
            confidence += 8.0
        if liquidity_event in {"sweep_high_reject", "supply_absorption"}:
            confidence += 6.0
        if liquidity_event in {"sweep_low_reclaim", "demand_absorption"}:
            confidence -= 12.0

    if chart_regime_state in {"chop", "squeeze"}:
        confidence -= 12.0

    return max(5.0, min(100.0, confidence))


def _display_symbol(symbol: str) -> str:
    return str(symbol or "").upper().strip().replace(".SA", "").replace("-USD", "USD")


def resolve_chart_timeframe(interval: str = "1D") -> str:
    return _CHART_INTERVAL_TO_TIMEFRAME.get(str(interval or "1D").upper(), "5m")


def _infer_profile(symbol: str) -> str:
    normalized = str(symbol or "").upper().strip()
    display = _display_symbol(normalized)
    compact = normalized.replace(".SA", "").replace("-", "").replace("/", "")

    if (
        normalized in _CRYPTO_UNIVERSE
        or display in _CRYPTO_DISPLAY_UNIVERSE
        or compact.endswith(("USD", "USDT", "USDC"))
    ):
        return "crypto"

    if (
        normalized in _BDR_UNIVERSE
        or display in _BDR_DISPLAY_UNIVERSE
        or (normalized.endswith(".SA") and display.endswith("34"))
    ):
        return "bdr"

    if normalized in _B3_UNIVERSE or display in _B3_DISPLAY_UNIVERSE or normalized.endswith(".SA"):
        return "b3_stock"

    return "us_stock"


def _build_ohlc_frame(ohlc: List[Dict[str, Any]]) -> pd.DataFrame:
    pd = _get_pandas()
    rows: List[Dict[str, Any]] = []

    for row in ohlc or []:
        if not isinstance(row, dict):
            continue

        rows.append(
            {
                "time": row.get("time"),
                "open": _safe_float(row.get("open")),
                "high": _safe_float(row.get("high")),
                "low": _safe_float(row.get("low")),
                "close": _safe_float(row.get("close")),
                "volume": _safe_float(row.get("volume")),
            }
        )

    frame = pd.DataFrame(rows)

    if frame.empty:
        return frame

    frame = frame.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    return frame


def _build_indicator_frame(
    frame: pd.DataFrame,
    breakout_lookback: int = 20,
    atr_period: int = 14,
    slope_lookback: int = 3,
    volume_lookback: int = 20,
) -> pd.DataFrame:
    pd = _get_pandas()
    df = frame.copy()

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    df["ema9"] = close.ewm(span=9, adjust=False).mean()
    df["ema21"] = close.ewm(span=21, adjust=False).mean()
    df["ema50"] = close.ewm(span=50, adjust=False).mean()
    typical_price = (high + low + close) / 3.0
    cumulative_volume = volume.cumsum()
    cumulative_value = (typical_price * volume).cumsum()
    df["vwap"] = (cumulative_value / cumulative_volume.where(cumulative_volume > 0)).ffill().fillna(df["ema21"])

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df["atr"] = tr.ewm(alpha=(1 / max(1, atr_period)), adjust=False).mean()
    df["atr_avg_day"] = df["atr"].rolling(48, min_periods=8).mean()
    df["atr_avg_hour"] = df["atr"].rolling(12, min_periods=4).mean()
    df["volume_avg"] = volume.rolling(volume_lookback, min_periods=max(5, volume_lookback // 3)).mean()
    df["resistance"] = high.shift(1).rolling(
        breakout_lookback,
        min_periods=max(5, breakout_lookback // 2),
    ).max()
    df["support"] = low.shift(1).rolling(
        breakout_lookback,
        min_periods=max(5, breakout_lookback // 2),
    ).min()
    df["slope21"] = (df["ema21"] - df["ema21"].shift(slope_lookback)) / max(1, slope_lookback)

    return df


def _neutral_payload(
    symbol: str,
    timeframe: str,
    profile: str,
    reason: str,
) -> Dict[str, Any]:
    display = _display_symbol(symbol)

    return {
        "ticker": display,
        "symbol": display,
        "engine": "trend_breakout_v1",
        "timeframe": timeframe,
        "profile": profile,
        "signal": "NEUTRAL",
        "score": 0.0,
        "trend": "sideways",
        "breakout": False,
        "pullback": False,
        "events": [],
        "latest_event": None,
        "context": {
            "reason": reason,
        },
    }


def _minimum_required_bars(timeframe: str, profile: str) -> int:
    normalized_timeframe = str(timeframe or "").lower()
    if normalized_timeframe in {"5m", "15m", "30m"}:
        return 24 if profile == "b3_stock" else 28
    return 35


def _parse_event_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        try:
            value = value.to_pydatetime()
        except Exception:
            return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_session_close_bar(time_value: Any, timeframe: str, profile: str) -> bool:
    if str(timeframe or "").lower() not in _INTRADAY_TIMEFRAMES:
        return False

    if isinstance(time_value, str) and time_value.strip():
        raw = time_value.strip()
        has_explicit_tz = raw.endswith("Z") or any(token in raw[10:] for token in ("+", "-"))
        if not has_explicit_tz:
            try:
                local_candidate = datetime.fromisoformat(raw)
                local_minute = (local_candidate.hour * 60) + local_candidate.minute
                if profile == "crypto":
                    return local_minute >= (23 * 60 + 55)
                if profile == "b3_stock":
                    return local_minute >= (17 * 60 + 55)
                return local_minute >= (19 * 60 + 55)
            except ValueError:
                pass

    parsed = _parse_event_datetime(time_value)
    if parsed is None:
        return False

    minute_of_day = (parsed.hour * 60) + parsed.minute
    if profile == "crypto":
        return minute_of_day >= (23 * 60 + 55)

    return minute_of_day >= (19 * 60 + 55)


def _effective_indicator_settings(settings: Dict[str, Any], bar_count: int) -> Dict[str, int]:
    return {
        "breakout_lookback": min(int(settings.get("breakout_lookback", 12)), max(6, bar_count // 3)),
        "atr_period": min(int(settings.get("atr_period", 14)), max(7, bar_count // 3)),
        "slope_lookback": min(int(settings.get("slope_lookback", 3)), max(2, bar_count // 12)),
        "volume_lookback": min(int(settings.get("volume_lookback", 20)), max(8, bar_count // 2)),
    }


def _warmup_bars(bar_count: int, timeframe: str, settings: Dict[str, Any]) -> int:
    normalized_timeframe = str(timeframe or "").lower()
    if normalized_timeframe in {"5m", "15m", "30m"}:
        base = max(10, int(min(bar_count - 8, max(12, bar_count * 0.22))))
    else:
        base = max(24, int(min(bar_count - 10, max(35, bar_count * 0.35))))
    return max(8, min(55, base, max(8, bar_count - 6)))


def build_trend_breakout_payload(
    symbol: str,
    ohlc: List[Dict[str, Any]],
    timeframe: str = "5m",
    ai_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    profile = _infer_profile(symbol)
    settings = _PROFILE_DEFAULTS[profile]
    display = _display_symbol(symbol)
    frame = _build_ohlc_frame(ohlc)
    min_bars = _minimum_required_bars(timeframe, profile)

    if frame.empty or len(frame) < min_bars:
        return _neutral_payload(display, timeframe, profile, "insufficient_data")

    effective_settings = _effective_indicator_settings(settings, len(frame))
    df = _build_indicator_frame(
        frame,
        breakout_lookback=effective_settings["breakout_lookback"],
        atr_period=effective_settings["atr_period"],
        slope_lookback=effective_settings["slope_lookback"],
        volume_lookback=effective_settings["volume_lookback"],
    )
    events: List[Dict[str, Any]] = []

    breakout_long_bar = -1
    breakout_short_bar = -1
    pullback_long_armed = False
    pullback_short_armed = False

    current_position = None
    entry_index = -1
    entry_price = 0.0
    best_price_after_entry = 0.0
    worst_price_after_entry = 0.0
    last_exit_index = -999

    latest_score = 0
    latest_signal = "NEUTRAL"
    latest_breakout = False
    latest_pullback = False
    latest_trend = "sideways"
    latest_coherence: Dict[str, Any] | None = None
    ai_bias = _build_ai_bias(ai_context, profile)

    warmup = _warmup_bars(len(df), timeframe, effective_settings)

    for index in range(len(df)):
        if index < warmup:
            continue

        row = df.iloc[index]
        prev_row = df.iloc[index - 1]

        atr_value = _safe_float(row["atr"])
        close = _safe_float(row["close"])
        open_price = _safe_float(row["open"])
        high = _safe_float(row["high"])
        low = _safe_float(row["low"])
        volume = _safe_float(row["volume"])
        volume_prev = _safe_float(prev_row["volume"])
        volume_avg = _safe_float(row["volume_avg"])

        if atr_value <= 0 or close <= 0:
            continue

        ema_fast = _safe_float(row["ema9"])
        ema_mid = _safe_float(row["ema21"])
        ema_slow = _safe_float(row["ema50"])
        vwap = _safe_float(row.get("vwap"), ema_mid) or ema_mid
        resistance = _safe_float(row["resistance"])
        support = _safe_float(row["support"])

        body = abs(close - open_price)
        candle_range = max(0.0, high - low)

        if close >= open_price:
            candle_top = close
            candle_bottom = open_price
        else:
            candle_top = open_price
            candle_bottom = close

        upper_wick = max(0.0, high - candle_top)
        lower_wick = max(0.0, candle_bottom - low)

        trend_spread = min(abs(ema_fast - ema_mid), abs(ema_mid - ema_slow))
        spread_atr = trend_spread / atr_value
        body_atr = body / atr_value
        atr_pct = atr_value / close
        volume_known = volume_avg > 0 and (volume > 0 or volume_prev > 0)
        volume_rel = 1.0 if not volume_known else volume / volume_avg

        vol_rel_day = 1.0
        if _safe_float(row["atr_avg_day"]) > 0:
            vol_rel_day = atr_value / _safe_float(row["atr_avg_day"])

        vol_rel_hour = 1.0
        if _safe_float(row["atr_avg_hour"]) > 0:
            vol_rel_hour = atr_value / _safe_float(row["atr_avg_hour"])

        slow_mature = len(df) >= 55 and index >= 42
        slow_long_ok = (ema_mid >= ema_slow) or (not slow_mature and close >= ema_mid)
        slow_short_ok = (ema_mid <= ema_slow) or (not slow_mature and close <= ema_mid)
        vwap_long_ok = close >= vwap or close > ema_fast
        vwap_short_ok = close <= vwap or close < ema_fast

        long_trend = (
            (ema_fast > ema_mid)
            and slow_long_ok
            and (_safe_float(row["slope21"]) > 0)
            and (spread_atr >= settings["spread_atr_min"])
            and vwap_long_ok
        )

        short_trend = (
            (ema_fast < ema_mid)
            and slow_short_ok
            and (_safe_float(row["slope21"]) < 0)
            and (spread_atr >= settings["spread_atr_min"])
            and vwap_short_ok
        )

        volatility_ok = (
            (atr_pct >= settings["atr_pct_min"])
            and (atr_pct <= settings["atr_pct_max"])
            and (vol_rel_day >= 0.8)
            and (vol_rel_day <= 1.8)
            and (vol_rel_hour >= 0.8)
            and (vol_rel_hour <= 1.8)
        )

        price_expansion = body_atr >= max(0.22, settings["body_atr_min"] * 0.70)
        volume_ok = volume_rel >= settings["volume_factor"] or (not volume_known and price_expansion)
        volume_pullback_ok = ((volume < volume_avg) and (volume < volume_prev)) or (not volume_known and body_atr < settings["body_atr_min"])
        volume_resume_ok = ((volume > volume_avg) and (volume > volume_prev)) or (not volume_known and price_expansion)

        candle_forte_long = (close > open_price) and (body_atr >= settings["body_atr_min"])
        candle_forte_short = (close < open_price) and (body_atr >= settings["body_atr_min"])

        wick_ok_long = (body > 0) and (upper_wick <= (body * settings["wick_max_ratio"]))
        wick_ok_short = (body > 0) and (lower_wick <= (body * settings["wick_max_ratio"]))

        dist_ema_ideal_long = abs(close - ema_mid) <= (atr_value * settings["ema_distance_atr"])
        dist_ema_ideal_short = dist_ema_ideal_long

        range_ok = candle_range <= (atr_value * settings["max_range_atr_mult"])
        body_ok = body <= (atr_value * settings["max_body_atr_mult"])

        # For stocks and BDRs, strong breakout candles often carry larger bodies.
        # We keep range and wick filters in the hard gate, and use the body cap as a quality bonus.
        setup_limpo_long = wick_ok_long
        setup_limpo_short = wick_ok_short

        buffer = atr_value * settings["buffer_atr_mult"]
        buying_into_resistance = (
            resistance > 0
            and close <= (resistance + buffer)
            and ((resistance - close) / atr_value) < settings.get("resistance_room_atr", 0.4)
        )
        selling_into_support = (
            support > 0
            and close >= (support - buffer)
            and ((close - support) / atr_value) < settings.get("support_room_atr", 0.4)
        )

        resistance_reclaim_long = (
            resistance > 0
            and volatility_ok
            and volume_ok
            and candle_forte_long
            and setup_limpo_long
            and high > (resistance + buffer)
            and close >= (resistance + (buffer * 0.20))
            and close > max(ema_fast, ema_mid, vwap)
            and close >= _safe_float(prev_row["close"])
            and (ema_fast >= ema_mid or _safe_float(row["slope21"]) > 0)
        )
        support_reject_short = (
            support > 0
            and volatility_ok
            and volume_ok
            and candle_forte_short
            and setup_limpo_short
            and low < (support - buffer)
            and close <= (support - (buffer * 0.20))
            and close < min(ema_fast, ema_mid, vwap)
            and close <= _safe_float(prev_row["close"])
            and (ema_fast <= ema_mid or _safe_float(row["slope21"]) < 0)
        )

        long_breakout = (
            (long_trend or resistance_reclaim_long)
            and volatility_ok
            and volume_ok
            and candle_forte_long
            and setup_limpo_long
            and (close > (resistance + buffer))
        )

        short_breakout = (
            (short_trend or support_reject_short)
            and volatility_ok
            and volume_ok
            and candle_forte_short
            and setup_limpo_short
            and (close < (support - buffer))
        )

        chart_regime_state = _classify_chart_regime(
            long_trend=long_trend,
            short_trend=short_trend,
            long_breakout=long_breakout,
            short_breakout=short_breakout,
            spread_atr=spread_atr,
            body_atr=body_atr,
            volume_rel=volume_rel,
            vol_rel_day=vol_rel_day,
            volatility_ok=volatility_ok,
        )
        liquidity_event = _detect_liquidity_event(
            open_price=open_price,
            close=close,
            high=high,
            low=low,
            resistance=resistance,
            support=support,
            buffer=buffer,
            body=body,
            upper_wick=upper_wick,
            lower_wick=lower_wick,
            body_atr=body_atr,
            volume_rel=volume_rel,
        )
        if resistance_reclaim_long and not long_breakout and liquidity_event not in {"sweep_high_reject", "supply_absorption"}:
            chart_regime_state = "reversal_up"
        if support_reject_short and not short_breakout and liquidity_event not in {"sweep_low_reclaim", "demand_absorption"}:
            chart_regime_state = "reversal_down"

        if long_breakout:
            breakout_long_bar = index
            pullback_long_armed = False

        if short_breakout:
            breakout_short_bar = index
            pullback_short_armed = False

        breakout_recente_long = breakout_long_bar >= 0 and (index - breakout_long_bar) <= settings["pullback_max_bars"]
        breakout_recente_short = breakout_short_bar >= 0 and (index - breakout_short_bar) <= settings["pullback_max_bars"]

        touch_long_ema = ((low <= ema_fast <= high) or (low <= ema_mid <= high))
        touch_short_ema = touch_long_ema

        pullback_fraco_long = (
            breakout_recente_long
            and long_trend
            and touch_long_ema
            and ((close <= open_price) or (body_atr < settings["body_atr_min"]))
            and volume_pullback_ok
        )

        pullback_fraco_short = (
            breakout_recente_short
            and short_trend
            and touch_short_ema
            and ((close >= open_price) or (body_atr < settings["body_atr_min"]))
            and volume_pullback_ok
        )

        if pullback_fraco_long:
            pullback_long_armed = True

        if pullback_fraco_short:
            pullback_short_armed = True

        if not breakout_recente_long:
            pullback_long_armed = False

        if not breakout_recente_short:
            pullback_short_armed = False

        long_pullback = (
            pullback_long_armed
            and long_trend
            and candle_forte_long
            and wick_ok_long
            and (close > _safe_float(prev_row["high"]))
            and (lower_wick >= (body * settings["reject_wick_min_ratio"]))
            and volume_resume_ok
        )

        short_pullback = (
            pullback_short_armed
            and short_trend
            and candle_forte_short
            and wick_ok_short
            and (close < _safe_float(prev_row["low"]))
            and (upper_wick >= (body * settings["reject_wick_min_ratio"]))
            and volume_resume_ok
        )

        continuation_volume_ok = volume_rel >= max(0.90, settings["volume_factor"] - 0.12) or (not volume_known and price_expansion)
        long_continuation = (
            long_trend
            and volatility_ok
            and continuation_volume_ok
            and close > ema_fast
            and close >= _safe_float(prev_row["close"])
            and body_atr >= max(0.18, settings["body_atr_min"] * 0.55)
            and not buying_into_resistance
            and liquidity_event not in {"sweep_high_reject", "supply_absorption"}
        )
        short_continuation = (
            short_trend
            and volatility_ok
            and continuation_volume_ok
            and close < ema_fast
            and close <= _safe_float(prev_row["close"])
            and body_atr >= max(0.18, settings["body_atr_min"] * 0.55)
            and not selling_into_support
            and liquidity_event not in {"sweep_low_reclaim", "demand_absorption"}
        )
        if long_pullback:
            pullback_long_armed = False

        if short_pullback:
            pullback_short_armed = False

        score_long = 0
        score_short = 0

        if long_trend:
            score_long += 3
        if volatility_ok:
            score_long += 2
        if volume_ok:
            score_long += 2
        if candle_forte_long:
            score_long += 2
        if long_breakout:
            score_long += 3
        if long_pullback:
            score_long += 3
        if long_continuation:
            score_long += 2
        if resistance_reclaim_long:
            score_long += 3
        if dist_ema_ideal_long:
            score_long += 1
        if body_ok:
            score_long += 1
        if liquidity_event in {"sweep_low_reclaim", "demand_absorption"}:
            score_long += 1

        if short_trend:
            score_short += 3
        if volatility_ok:
            score_short += 2
        if volume_ok:
            score_short += 2
        if candle_forte_short:
            score_short += 2
        if short_breakout:
            score_short += 3
        if short_pullback:
            score_short += 3
        if short_continuation:
            score_short += 2
        if support_reject_short:
            score_short += 3
        if dist_ema_ideal_short:
            score_short += 1
        if body_ok:
            score_short += 1
        if liquidity_event in {"sweep_high_reject", "supply_absorption"}:
            score_short += 1

        long_liquidity_reversal = (
            liquidity_event in {"sweep_low_reclaim", "demand_absorption"}
            and close > ema_fast
            and close >= _safe_float(prev_row["close"])
            and score_long >= max(5, settings["score_min"] - 1)
        )
        short_liquidity_reversal = (
            liquidity_event in {"sweep_high_reject", "supply_absorption"}
            and close < ema_fast
            and close <= _safe_float(prev_row["close"])
            and score_short >= max(5, settings["score_min"] - 1)
        )
        long_trend_acceptance = (
            chart_regime_state == "trend_up"
            and close > max(ema_mid, vwap)
            and close >= _safe_float(prev_row["close"])
            and body_atr >= max(0.16, settings["body_atr_min"] * 0.50)
            and liquidity_event not in {"sweep_high_reject", "supply_absorption"}
            and (not buying_into_resistance or candle_forte_long or close > resistance)
        )
        short_trend_acceptance = (
            chart_regime_state == "trend_down"
            and close < min(ema_mid, vwap)
            and close <= _safe_float(prev_row["close"])
            and body_atr >= max(0.16, settings["body_atr_min"] * 0.50)
            and liquidity_event not in {"sweep_low_reclaim", "demand_absorption"}
            and (not selling_into_support or candle_forte_short or close < support)
        )

        score_long += int(ai_bias["long_bonus"])
        score_short += int(ai_bias["short_bonus"])

        required_score_long = max(5, settings["score_min"] + int(ai_bias["threshold_adjust"]))
        required_score_short = max(5, settings["score_min"] + int(ai_bias["threshold_adjust"]))
        trend_strength_score = max(
            0.0,
            min(100.0, spread_atr * 34.0 + (22.0 if long_trend or short_trend else 0.0)),
        )
        breakout_state = "ready_to_break" if (long_breakout or short_breakout) else (
            "building_pressure" if (breakout_recente_long or breakout_recente_short) else ai_bias.get("breakout_probability_state")
        )
        coherence_row = _coherence_context_row(
            display=display,
            ai_bias=ai_bias,
            close=close,
            ema_mid=vwap,
            volume_rel=volume_rel,
            volume_known=volume_known,
            trend_strength=trend_strength_score,
            score_long=score_long,
            score_short=score_short,
            breakout_state=str(breakout_state or ""),
            chart_regime_state=chart_regime_state,
            liquidity_event=liquidity_event,
        )

        long_entry = False
        short_entry = False
        event_reason = None
        long_confidence = _setup_confidence(
            side="long",
            score_side=score_long,
            score_opposite=score_short,
            required_score=required_score_long,
            trend_strength=trend_strength_score,
            volume_rel=volume_rel,
            chart_regime_state=chart_regime_state,
            liquidity_event=liquidity_event,
        )
        short_confidence = _setup_confidence(
            side="short",
            score_side=score_short,
            score_opposite=score_long,
            required_score=required_score_short,
            trend_strength=trend_strength_score,
            volume_rel=volume_rel,
            chart_regime_state=chart_regime_state,
            liquidity_event=liquidity_event,
        )
        if not volume_known:
            long_confidence = max(5.0, long_confidence - 6.0)
            short_confidence = max(5.0, short_confidence - 6.0)

        if current_position is None:
            cooldown_bars = int(settings.get("cooldown_bars_after_exit", 2))
            in_cooldown = (index - last_exit_index) < cooldown_bars
            strong_long_override = (
                volume_rel >= (settings["volume_factor"] + 0.35)
                and score_long >= (score_short + settings["min_score_edge"] + 3)
            )
            strong_short_override = (
                volume_rel >= (settings["volume_factor"] + 0.35)
                and score_short >= (score_long + settings["min_score_edge"] + 3)
            )
            if (
                not ai_bias["long_block"]
                and (not in_cooldown or strong_long_override)
                and long_pullback
                and not buying_into_resistance
                and score_long >= required_score_long
                and score_long >= (score_short + settings["min_score_edge"])
            ):
                long_entry = True
                event_reason = "pullback_resume"
            elif (
                not ai_bias["short_block"]
                and (not in_cooldown or strong_short_override)
                and short_pullback
                and not selling_into_support
                and score_short >= required_score_short
                and score_short >= (score_long + settings["min_score_edge"])
            ):
                short_entry = True
                event_reason = "pullback_resume"
            elif (
                not ai_bias["long_block"]
                and (not in_cooldown or strong_long_override)
                and long_breakout
                and score_long >= required_score_long
                and score_long >= (score_short + settings["min_score_edge"])
            ):
                long_entry = True
                event_reason = "breakout"
            elif (
                not ai_bias["short_block"]
                and (not in_cooldown or strong_short_override)
                and short_breakout
                and score_short >= required_score_short
                and score_short >= (score_long + settings["min_score_edge"])
            ):
                short_entry = True
                event_reason = "breakout"
            elif (
                not ai_bias["long_block"]
                and (not in_cooldown or strong_long_override)
                and resistance_reclaim_long
                and long_confidence >= 60
                and score_long >= max(5, required_score_long - 1)
                and score_long >= (score_short + settings["min_score_edge"])
            ):
                long_entry = True
                event_reason = "resistance_reclaim"
            elif (
                not ai_bias["short_block"]
                and (not in_cooldown or strong_short_override)
                and support_reject_short
                and short_confidence >= 60
                and score_short >= max(5, required_score_short - 1)
                and score_short >= (score_long + settings["min_score_edge"])
            ):
                short_entry = True
                event_reason = "support_reject"
            elif (
                not ai_bias["long_block"]
                and (not in_cooldown or strong_long_override)
                and long_liquidity_reversal
                and long_confidence >= 66
                and score_long >= (score_short + settings["min_score_edge"])
            ):
                long_entry = True
                event_reason = "liquidity_reversal"
            elif (
                not ai_bias["short_block"]
                and (not in_cooldown or strong_short_override)
                and short_liquidity_reversal
                and short_confidence >= 66
                and score_short >= (score_long + settings["min_score_edge"])
            ):
                short_entry = True
                event_reason = "liquidity_reversal"
            elif (
                not ai_bias["long_block"]
                and (not in_cooldown or strong_long_override)
                and long_trend_acceptance
                and long_confidence >= 60
                and (profile != "bdr" or (volume_ok and long_confidence >= 72))
                and score_long >= required_score_long
                and score_long >= (score_short + settings["min_score_edge"])
            ):
                long_entry = True
                event_reason = "trend_acceptance"
            elif (
                not ai_bias["short_block"]
                and (not in_cooldown or strong_short_override)
                and short_trend_acceptance
                and short_confidence >= 60
                and (profile != "bdr" or (volume_ok and short_confidence >= 72))
                and score_short >= required_score_short
                and score_short >= (score_long + settings["min_score_edge"])
            ):
                short_entry = True
                event_reason = "trend_acceptance"
            elif (
                not ai_bias["long_block"]
                and (not in_cooldown or strong_long_override)
                and long_continuation
                and long_confidence >= 58
                and score_long >= required_score_long
                and score_long >= (score_short + settings["min_score_edge"])
            ):
                long_entry = True
                event_reason = "trend_continuation"
            elif (
                not ai_bias["short_block"]
                and (not in_cooldown or strong_short_override)
                and short_continuation
                and short_confidence >= 58
                and score_short >= required_score_short
                and score_short >= (score_long + settings["min_score_edge"])
            ):
                short_entry = True
                event_reason = "trend_continuation"

        event_time = row["time"]
        long_coherence = evaluate_trade_coherence(coherence_row, "BUY", bullish=score_long, bearish=score_short)
        short_coherence = evaluate_trade_coherence(coherence_row, "SHORT", bullish=score_long, bearish=score_short)

        if long_entry and long_coherence["coherence_status"] == "blocked":
            long_entry = False
            latest_coherence = long_coherence
        if short_entry and short_coherence["coherence_status"] == "blocked":
            short_entry = False
            latest_coherence = short_coherence

        if long_entry:
            events.append(
                _event_payload(
                    event_type="BUY",
                    price=close,
                    time_value=event_time,
                    score=score_long,
                    reason=event_reason,
                    coherence=long_coherence,
                    confidence=long_confidence,
                    chart_regime_state=chart_regime_state,
                    liquidity_event=liquidity_event,
                )
            )
            current_position = "long"
            entry_index = index
            entry_price = close
            best_price_after_entry = high
            worst_price_after_entry = low
            latest_signal = "BUY"
            latest_coherence = long_coherence
        elif short_entry:
            events.append(
                _event_payload(
                    event_type="SHORT",
                    price=close,
                    time_value=event_time,
                    score=score_short,
                    reason=event_reason,
                    coherence=short_coherence,
                    confidence=short_confidence,
                    chart_regime_state=chart_regime_state,
                    liquidity_event=liquidity_event,
                )
            )
            current_position = "short"
            entry_index = index
            entry_price = close
            best_price_after_entry = high
            worst_price_after_entry = low
            latest_signal = "SHORT"
            latest_coherence = short_coherence
        elif current_position == "long":
            best_price_after_entry = max(best_price_after_entry, high, close)
            worst_price_after_entry = min(worst_price_after_entry, low, close)
            profit_atr = (best_price_after_entry - entry_price) / atr_value if entry_price > 0 else 0.0
            long_continuation_intact = (
                long_trend
                and close >= min(ema_mid, vwap)
                and score_long >= (score_short + settings["min_score_edge"])
                and liquidity_event not in {"sweep_high_reject", "supply_absorption"}
            )
            protect_profit = (
                profit_atr >= 1.35
                and close < ema_fast
                and close < _safe_float(prev_row["low"])
                and score_short >= (score_long - 1)
                and not long_continuation_intact
            )
            micro_structure_loss = (
                close < min(ema_mid, vwap)
                and score_short >= (score_long + settings["min_score_edge"])
                and volume_rel >= 0.95
            )
            confirmed_opposite = (
                (short_pullback or short_breakout or short_liquidity_reversal or short_continuation)
                and score_short >= required_score_short
                and short_confidence >= 66
                and close < min(ema_mid, vwap)
            )
            time_stop = ((index - entry_index) >= settings["max_hold_bars"]) and not long_continuation_intact
            should_exit_long = (
                time_stop
                or micro_structure_loss
                or ai_bias["exit_long_on_ai"]
                or protect_profit
                or confirmed_opposite
            )

            if should_exit_long:
                reason = "trend_loss"
                if ai_bias["exit_long_on_ai"]:
                    reason = "ai_regime_flip"
                elif confirmed_opposite:
                    reason = "opposite_signal"
                elif protect_profit:
                    reason = "protect_profit"
                elif micro_structure_loss:
                    reason = "micro_structure_loss"
                sell_coherence = evaluate_trade_coherence(coherence_row, "SELL", bullish=score_long, bearish=score_short)

                events.append(
                    _event_payload(
                        event_type="SELL",
                        price=close,
                        time_value=event_time,
                        score=score_short if reason == "opposite_signal" else score_long,
                        reason=reason,
                        coherence=sell_coherence,
                        confidence=short_confidence if reason == "opposite_signal" else long_confidence,
                        chart_regime_state=chart_regime_state,
                        liquidity_event=liquidity_event,
                    )
                )
                current_position = None
                entry_index = -1
                entry_price = 0.0
                best_price_after_entry = 0.0
                worst_price_after_entry = 0.0
                last_exit_index = index
                latest_signal = "SELL"
                latest_coherence = sell_coherence
        elif current_position == "short":
            best_price_after_entry = max(best_price_after_entry, high, close)
            worst_price_after_entry = min(worst_price_after_entry, low, close)
            profit_atr = (entry_price - worst_price_after_entry) / atr_value if entry_price > 0 else 0.0
            short_continuation_intact = (
                short_trend
                and close <= max(ema_mid, vwap)
                and score_short >= (score_long + settings["min_score_edge"])
                and liquidity_event not in {"sweep_low_reclaim", "demand_absorption"}
            )
            protect_profit = (
                profit_atr >= 1.35
                and close > ema_fast
                and close > _safe_float(prev_row["high"])
                and score_long >= (score_short - 1)
                and not short_continuation_intact
            )
            micro_structure_loss = (
                close > max(ema_mid, vwap)
                and score_long >= (score_short + settings["min_score_edge"])
                and volume_rel >= 0.95
            )
            confirmed_opposite = (
                (long_pullback or long_breakout or long_liquidity_reversal or long_continuation)
                and score_long >= required_score_long
                and long_confidence >= 66
                and close > max(ema_mid, vwap)
            )
            time_stop = ((index - entry_index) >= settings["max_hold_bars"]) and not short_continuation_intact
            should_exit_short = (
                time_stop
                or micro_structure_loss
                or ai_bias["exit_short_on_ai"]
                or protect_profit
                or confirmed_opposite
            )

            if should_exit_short:
                reason = "trend_loss"
                if ai_bias["exit_short_on_ai"]:
                    reason = "ai_regime_flip"
                elif confirmed_opposite:
                    reason = "opposite_signal"
                elif protect_profit:
                    reason = "protect_profit"
                elif micro_structure_loss:
                    reason = "micro_structure_loss"
                cover_coherence = evaluate_trade_coherence(coherence_row, "COVER", bullish=score_long, bearish=score_short)

                events.append(
                    _event_payload(
                        event_type="COVER",
                        price=close,
                        time_value=event_time,
                        score=score_long if reason == "opposite_signal" else score_short,
                        reason=reason,
                        coherence=cover_coherence,
                        confidence=long_confidence if reason == "opposite_signal" else short_confidence,
                        chart_regime_state=chart_regime_state,
                        liquidity_event=liquidity_event,
                    )
                )
                current_position = None
                entry_index = -1
                entry_price = 0.0
                best_price_after_entry = 0.0
                worst_price_after_entry = 0.0
                last_exit_index = index
                latest_signal = "COVER"
                latest_coherence = cover_coherence

        latest_score = max(score_long, score_short)
        latest_breakout = bool(long_breakout or short_breakout)
        latest_pullback = bool(long_pullback or short_pullback)

        if long_trend:
            latest_trend = "up"
        elif short_trend:
            latest_trend = "down"
        else:
            latest_trend = "sideways"

        if latest_signal == "NEUTRAL":
            if current_position == "long":
                latest_signal = "BUY"
            elif current_position == "short":
                latest_signal = "SHORT"
            elif (
                not ai_bias["long_block"]
                and score_long >= required_score_long
                and long_confidence >= 58
                and (profile != "bdr" or volume_ok)
            ):
                latest_signal = "WATCH_BUY"
            elif (
                not ai_bias["short_block"]
                and score_short >= required_score_short
                and short_confidence >= 58
                and (profile != "bdr" or volume_ok)
            ):
                latest_signal = "WATCH_SHORT"
        if latest_coherence is None:
            watch_action = "BUY" if score_long >= score_short else "SHORT"
            latest_coherence = evaluate_trade_coherence(coherence_row, watch_action, bullish=score_long, bearish=score_short)

    if current_position in {"long", "short"} and _is_session_close_bar(df.iloc[-1]["time"], timeframe, profile):
        final_row = df.iloc[-1]
        final_close = _safe_float(final_row["close"])
        if final_close > 0 and "coherence_row" in locals():
            if current_position == "long":
                exit_type = "SELL"
                exit_score = score_long if "score_long" in locals() else latest_score
                exit_confidence = long_confidence if "long_confidence" in locals() else None
            else:
                exit_type = "COVER"
                exit_score = score_short if "score_short" in locals() else latest_score
                exit_confidence = short_confidence if "short_confidence" in locals() else None

            close_coherence = evaluate_trade_coherence(
                coherence_row,
                exit_type,
                bullish=score_long if "score_long" in locals() else latest_score,
                bearish=score_short if "score_short" in locals() else latest_score,
            )
            events.append(
                _event_payload(
                    event_type=exit_type,
                    price=final_close,
                    time_value=final_row["time"],
                    score=exit_score,
                    reason="session_close",
                    coherence=close_coherence,
                    confidence=exit_confidence,
                    chart_regime_state=chart_regime_state if "chart_regime_state" in locals() else latest_trend,
                    liquidity_event=liquidity_event if "liquidity_event" in locals() else None,
                )
            )
            current_position = None
            latest_signal = exit_type
            latest_coherence = close_coherence

    latest_close = _safe_float(df.iloc[-1]["close"])
    latest_volume_rel = 1.0
    last_volume_avg = _safe_float(df.iloc[-1]["volume_avg"])
    if last_volume_avg > 0:
        latest_volume_rel = _safe_float(df.iloc[-1]["volume"]) / last_volume_avg

    latest_atr = _safe_float(df.iloc[-1]["atr"])
    latest_atr_pct = 0.0 if latest_close <= 0 else latest_atr / latest_close

    return {
        "ticker": display,
        "symbol": display,
        "engine": "trend_breakout_v1",
        "timeframe": timeframe,
        "profile": profile,
        "signal": latest_signal,
        "score": round(latest_score, 2),
        "trend": latest_trend,
        "breakout": latest_breakout,
        "pullback": latest_pullback,
        "events": events[-50:],
        "latest_event": events[-1] if events else None,
        "context": {
            "latest_close": round(latest_close, 4),
            "atr": round(latest_atr, 6),
            "atr_pct": round(latest_atr_pct, 6),
            "volume_rel": round(latest_volume_rel, 4),
            "ema9": round(_safe_float(df.iloc[-1]["ema9"]), 4),
            "ema21": round(_safe_float(df.iloc[-1]["ema21"]), 4),
            "ema50": round(_safe_float(df.iloc[-1]["ema50"]), 4),
            "vwap": round(_safe_float(df.iloc[-1].get("vwap")), 4),
            "warmup_bars": warmup,
            "bars_used": int(len(df)),
            "chart_regime_state": chart_regime_state if "chart_regime_state" in locals() else "unknown",
            "liquidity_event": liquidity_event if "liquidity_event" in locals() else "none",
            "long_confidence": round(long_confidence, 1) if "long_confidence" in locals() else 0.0,
            "short_confidence": round(short_confidence, 1) if "short_confidence" in locals() else 0.0,
            "ai_bias": {
                "market_regime_state": ai_bias["market_regime_state"],
                "market_regime_score": round(ai_bias["market_regime_score"], 1),
                "smart_money_score": round(ai_bias["smart_money_score"], 1),
                "master_score": round(ai_bias["master_score"], 1),
                "long_block": bool(ai_bias["long_block"]),
                "short_block": bool(ai_bias["short_block"]),
            },
            "trade_coherence": latest_coherence or {},
        },
    }
