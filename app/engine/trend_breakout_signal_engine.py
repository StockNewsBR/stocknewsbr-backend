import logging
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger("stocknewsbr.trend_breakout_signal_engine")

_CHART_INTERVAL_TO_TIMEFRAME = {
    "1D": "5m",
    "1W": "30m",
    "1M": "1d",
}

_PROFILE_DEFAULTS = {
    "b3_stock": {
        "breakout_lookback": 12,
        "atr_period": 14,
        "slope_lookback": 3,
        "volume_lookback": 20,
        "volume_factor": 1.04,
        "atr_pct_min": 0.0015,
        "atr_pct_max": 0.0800,
        "body_atr_min": 0.32,
        "spread_atr_min": 0.10,
        "buffer_atr_mult": 0.06,
        "ema_distance_atr": 2.40,
        "max_range_atr_mult": 2.25,
        "max_body_atr_mult": 1.60,
        "score_min": 7,
        "pullback_max_bars": 4,
        "max_hold_bars": 8,
        "wick_max_ratio": 0.38,
        "reject_wick_min_ratio": 0.12,
        "min_score_edge": 1,
    },
    "bdr": {
        "breakout_lookback": 12,
        "atr_period": 14,
        "slope_lookback": 3,
        "volume_lookback": 20,
        "volume_factor": 1.02,
        "atr_pct_min": 0.0012,
        "atr_pct_max": 0.1000,
        "body_atr_min": 0.28,
        "spread_atr_min": 0.09,
        "buffer_atr_mult": 0.05,
        "ema_distance_atr": 2.70,
        "max_range_atr_mult": 2.40,
        "max_body_atr_mult": 1.70,
        "score_min": 7,
        "pullback_max_bars": 4,
        "max_hold_bars": 8,
        "wick_max_ratio": 0.40,
        "reject_wick_min_ratio": 0.10,
        "min_score_edge": 1,
    },
    "us_stock": {
        "breakout_lookback": 12,
        "atr_period": 14,
        "slope_lookback": 3,
        "volume_lookback": 20,
        "volume_factor": 1.02,
        "atr_pct_min": 0.0010,
        "atr_pct_max": 0.0800,
        "body_atr_min": 0.25,
        "spread_atr_min": 0.08,
        "buffer_atr_mult": 0.05,
        "ema_distance_atr": 3.00,
        "max_range_atr_mult": 2.50,
        "max_body_atr_mult": 1.80,
        "score_min": 7,
        "pullback_max_bars": 4,
        "max_hold_bars": 9,
        "wick_max_ratio": 0.42,
        "reject_wick_min_ratio": 0.10,
        "min_score_edge": 1,
    },
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return default


def _display_symbol(symbol: str) -> str:
    return str(symbol or "").upper().strip().replace(".SA", "").replace("-USD", "USD")


def resolve_chart_timeframe(interval: str = "1D") -> str:
    return _CHART_INTERVAL_TO_TIMEFRAME.get(str(interval or "1D").upper(), "5m")


def _infer_profile(symbol: str) -> str:
    normalized = str(symbol or "").upper().strip()
    display = _display_symbol(normalized)

    if normalized.endswith(".SA") and display.endswith("34"):
        return "bdr"

    if normalized.endswith(".SA"):
        return "b3_stock"

    return "us_stock"


def _build_ohlc_frame(ohlc: List[Dict[str, Any]]) -> pd.DataFrame:
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
    df = frame.copy()

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    df["ema9"] = close.ewm(span=9, adjust=False).mean()
    df["ema21"] = close.ewm(span=21, adjust=False).mean()
    df["ema50"] = close.ewm(span=50, adjust=False).mean()

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


def build_trend_breakout_payload(
    symbol: str,
    ohlc: List[Dict[str, Any]],
    timeframe: str = "5m",
) -> Dict[str, Any]:
    profile = _infer_profile(symbol)
    settings = _PROFILE_DEFAULTS[profile]
    display = _display_symbol(symbol)
    frame = _build_ohlc_frame(ohlc)

    if frame.empty or len(frame) < 60:
        return _neutral_payload(display, timeframe, profile, "insufficient_data")

    df = _build_indicator_frame(
        frame,
        breakout_lookback=int(settings.get("breakout_lookback", 12)),
        atr_period=int(settings.get("atr_period", 14)),
        slope_lookback=int(settings.get("slope_lookback", 3)),
        volume_lookback=int(settings.get("volume_lookback", 20)),
    )
    events: List[Dict[str, Any]] = []

    breakout_long_bar = -1
    breakout_short_bar = -1
    pullback_long_armed = False
    pullback_short_armed = False

    current_position = None
    entry_index = -1

    latest_score = 0
    latest_signal = "NEUTRAL"
    latest_breakout = False
    latest_pullback = False
    latest_trend = "sideways"

    warmup = 55

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
        volume_rel = 1.0 if volume_avg <= 0 else volume / volume_avg

        vol_rel_day = 1.0
        if _safe_float(row["atr_avg_day"]) > 0:
            vol_rel_day = atr_value / _safe_float(row["atr_avg_day"])

        vol_rel_hour = 1.0
        if _safe_float(row["atr_avg_hour"]) > 0:
            vol_rel_hour = atr_value / _safe_float(row["atr_avg_hour"])

        long_trend = (
            (ema_fast > ema_mid)
            and (ema_mid > ema_slow)
            and (_safe_float(row["slope21"]) > 0)
            and (spread_atr >= settings["spread_atr_min"])
        )

        short_trend = (
            (ema_fast < ema_mid)
            and (ema_mid < ema_slow)
            and (_safe_float(row["slope21"]) < 0)
            and (spread_atr >= settings["spread_atr_min"])
        )

        volatility_ok = (
            (atr_pct >= settings["atr_pct_min"])
            and (atr_pct <= settings["atr_pct_max"])
            and (vol_rel_day >= 0.8)
            and (vol_rel_day <= 1.8)
            and (vol_rel_hour >= 0.8)
            and (vol_rel_hour <= 1.8)
        )

        volume_ok = volume_rel >= settings["volume_factor"]
        volume_pullback_ok = (volume < volume_avg) and (volume < volume_prev)
        volume_resume_ok = (volume > volume_avg) and (volume > volume_prev)

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

        long_breakout = (
            long_trend
            and volatility_ok
            and volume_ok
            and candle_forte_long
            and setup_limpo_long
            and (close > (resistance + buffer))
        )

        short_breakout = (
            short_trend
            and volatility_ok
            and volume_ok
            and candle_forte_short
            and setup_limpo_short
            and (close < (support - buffer))
        )

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
        if dist_ema_ideal_long:
            score_long += 1
        if body_ok:
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
        if dist_ema_ideal_short:
            score_short += 1
        if body_ok:
            score_short += 1

        long_entry = False
        short_entry = False
        event_reason = None

        if current_position is None:
            if long_pullback and score_long >= settings["score_min"] and score_long >= (score_short + settings["min_score_edge"]):
                long_entry = True
                event_reason = "pullback_resume"
            elif short_pullback and score_short >= settings["score_min"] and score_short >= (score_long + settings["min_score_edge"]):
                short_entry = True
                event_reason = "pullback_resume"
            elif long_breakout and score_long >= settings["score_min"] and score_long >= (score_short + settings["min_score_edge"]):
                long_entry = True
                event_reason = "breakout"
            elif short_breakout and score_short >= settings["score_min"] and score_short >= (score_long + settings["min_score_edge"]):
                short_entry = True
                event_reason = "breakout"

        event_time = row["time"]

        if long_entry:
            events.append(
                {
                    "type": "BUY",
                    "price": round(close, 4),
                    "time": event_time,
                    "score": score_long,
                    "reason": event_reason,
                    "strategy": "trend_breakout_v1",
                }
            )
            current_position = "long"
            entry_index = index
            latest_signal = "BUY"
        elif short_entry:
            events.append(
                {
                    "type": "SHORT",
                    "price": round(close, 4),
                    "time": event_time,
                    "score": score_short,
                    "reason": event_reason,
                    "strategy": "trend_breakout_v1",
                }
            )
            current_position = "short"
            entry_index = index
            latest_signal = "SHORT"
        elif current_position == "long":
            should_exit_long = (
                ((index - entry_index) >= settings["max_hold_bars"])
                or (close < ema_mid)
                or (
                    (short_pullback or short_breakout)
                    and score_short >= settings["score_min"]
                )
            )

            if should_exit_long:
                reason = "trend_loss"
                if (short_pullback or short_breakout) and score_short >= settings["score_min"]:
                    reason = "opposite_signal"

                events.append(
                    {
                        "type": "SELL",
                        "price": round(close, 4),
                        "time": event_time,
                        "score": score_short if reason == "opposite_signal" else score_long,
                        "reason": reason,
                        "strategy": "trend_breakout_v1",
                    }
                )
                current_position = None
                entry_index = -1
                latest_signal = "SELL"
        elif current_position == "short":
            should_exit_short = (
                ((index - entry_index) >= settings["max_hold_bars"])
                or (close > ema_mid)
                or (
                    (long_pullback or long_breakout)
                    and score_long >= settings["score_min"]
                )
            )

            if should_exit_short:
                reason = "trend_loss"
                if (long_pullback or long_breakout) and score_long >= settings["score_min"]:
                    reason = "opposite_signal"

                events.append(
                    {
                        "type": "COVER",
                        "price": round(close, 4),
                        "time": event_time,
                        "score": score_long if reason == "opposite_signal" else score_short,
                        "reason": reason,
                        "strategy": "trend_breakout_v1",
                    }
                )
                current_position = None
                entry_index = -1
                latest_signal = "COVER"

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
            elif score_long >= settings["score_min"]:
                latest_signal = "WATCH_BUY"
            elif score_short >= settings["score_min"]:
                latest_signal = "WATCH_SHORT"

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
        },
    }
