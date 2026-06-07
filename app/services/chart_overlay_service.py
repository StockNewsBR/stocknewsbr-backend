from typing import Iterable, List


def _ema(values: Iterable[float], period: int) -> List[float]:
    values = [float(value or 0) for value in values]

    if not values:
        return []

    multiplier = 2 / (period + 1)
    ema_values = [values[0]]

    for value in values[1:]:
        ema_values.append((value - ema_values[-1]) * multiplier + ema_values[-1])

    return ema_values


def _supertrend(highs: List[float], lows: List[float], closes: List[float], period: int = 10, multiplier: float = 2.2):
    if not highs or not lows or not closes or len(closes) < 2:
        return [], []

    true_ranges = [max(highs[0] - lows[0], 0)]
    for index in range(1, len(closes)):
        true_ranges.append(
            max(
                highs[index] - lows[index],
                abs(highs[index] - closes[index - 1]),
                abs(lows[index] - closes[index - 1]),
            )
        )

    atr_values = []
    for index, value in enumerate(true_ranges):
        if index == 0:
            atr_values.append(value)
            continue
        previous = atr_values[-1]
        atr_values.append(((previous * (period - 1)) + value) / period)

    final_upper = [0.0] * len(closes)
    final_lower = [0.0] * len(closes)
    trend_line = [None] * len(closes)
    trend_side = ["neutral"] * len(closes)

    for index in range(len(closes)):
        hl2 = (highs[index] + lows[index]) / 2
        basic_upper = hl2 + multiplier * atr_values[index]
        basic_lower = hl2 - multiplier * atr_values[index]

        if index == 0:
            final_upper[index] = basic_upper
            final_lower[index] = basic_lower
            trend_side[index] = "buy"
            trend_line[index] = final_lower[index]
            continue

        final_upper[index] = (
            basic_upper
            if basic_upper < final_upper[index - 1] or closes[index - 1] > final_upper[index - 1]
            else final_upper[index - 1]
        )
        final_lower[index] = (
            basic_lower
            if basic_lower > final_lower[index - 1] or closes[index - 1] < final_lower[index - 1]
            else final_lower[index - 1]
        )

        previous_line = trend_line[index - 1]
        if previous_line == final_upper[index - 1]:
            is_bullish = closes[index] > final_upper[index]
        else:
            is_bullish = closes[index] >= final_lower[index]

        trend_side[index] = "buy" if is_bullish else "sell"
        trend_line[index] = final_lower[index] if is_bullish else final_upper[index]

    return trend_line, trend_side


_TRADE_LABELS = {
    "BUY": "Buy Long",
    "SELL": "Close Long",
    "SHORT": "Sell Short",
    "COVER": "Close Short",
    "PRICE_EVENT": "Evento",
}


_TRADE_NOTES = {
    "BUY": "Entrada long",
    "SELL": "Saida long",
    "SHORT": "Entrada short",
    "COVER": "Saida short",
    "PRICE_EVENT": "Evento de preco",
}


_DISPLAY_EVENT_TYPE_MAP = {
    "BUY": "SHORT",
    "SELL": "COVER",
    "SHORT": "BUY",
    "COVER": "SELL",
    "PRICE_EVENT": "PRICE_EVENT",
}


def _trade_side(event_type: str):
    if event_type in {"BUY", "COVER"}:
        return "buy"
    if event_type in {"SELL", "SHORT"}:
        return "sell"
    return "neutral"


def _trade_marker_style(event_type: str):
    if event_type == "BUY":
        return "circle", "green"
    if event_type == "SELL":
        return "circle", "red"
    if event_type == "SHORT":
        return "square", "orange"
    if event_type == "COVER":
        return "diamond", "blue"
    return "circle", "gray"


def _derived_watch_marker(ticker: str, event_type: str, time_value, price, score, reason: str, trigger: str, invalidation: str, risk: str):
    return {
        "ticker": ticker,
        "type": "WATCH",
        "side": "neutral",
        "shape": "diamond",
        "color": "amber",
        "label": "Watch",
        "action_label": "Watch",
        "operational_note": "Aguardar",
        "time": time_value,
        "price": price,
        "score": score,
        "reason": reason,
        "reason_text": "Leitura tecnica derivada; nao e entrada operacional.",
        "trigger": trigger,
        "confirmation": trigger,
        "invalidation": invalidation,
        "risk": risk,
        "risk_level": "medio",
        "coherence_status": "derived_watch",
        "derived": True,
        "derived_from": event_type,
    }


def _derived_trade_marker(ticker: str, event_type: str, time_value, price, reason: str, trigger: str, invalidation: str, risk: str):
    side = _trade_side(event_type)
    shape, color = _trade_marker_style(event_type)
    return {
        "ticker": ticker,
        "type": event_type,
        "side": side,
        "shape": shape,
        "color": color,
        "label": _TRADE_LABELS.get(event_type, event_type.title()),
        "action_label": _TRADE_LABELS.get(event_type, event_type.title()),
        "operational_note": _TRADE_NOTES.get(event_type, event_type.title()),
        "time": time_value,
        "price": price,
        "reason": reason,
        "reason_text": "Sinal derivado do rompimento estrutural do gráfico com confirmação mínima de preço e volume.",
        "trigger": trigger,
        "confirmation": trigger,
        "invalidation": invalidation,
        "risk": risk,
        "risk_level": "medio",
        "coherence_status": "derived_breakout",
        "derived": True,
    }


def _latest_structure_trade_marker(ticker: str, ohlc: list, series: list, high_prices: list[float], low_prices: list[float], close_prices: list[float], volume_values: list[float]):
    if len(series) < 14 or not close_prices:
        return None

    index = len(series) - 1
    close = close_prices[index]
    if close <= 0:
        return None

    try:
        open_price = float(ohlc[index].get("open", close) or close)
    except Exception:
        open_price = close

    previous_highs = high_prices[max(0, index - 12) : index]
    previous_lows = low_prices[max(0, index - 12) : index]
    if not previous_highs or not previous_lows:
        return None

    current_volume = volume_values[index] if index < len(volume_values) else 0.0
    previous_volumes = [value for value in volume_values[max(0, index - 24) : index] if value > 0]
    if current_volume <= 0 or not previous_volumes:
        return None

    average_volume = max(sum(previous_volumes) / len(previous_volumes), 1.0)
    relative_volume = current_volume / average_volume
    resistance = max(previous_highs)
    support = min(previous_lows)
    band = max(resistance - support, abs(close) * 0.001, 0.0001)
    buffer = max(band * 0.015, abs(close) * 0.0004)
    marker_time = series[index].get("time")

    if close > resistance + buffer and close >= open_price and relative_volume >= 1.1:
        return _derived_trade_marker(
            ticker,
            "BUY",
            marker_time,
            min(low_prices[index], close),
            "latest_resistance_breakout",
            "Compra somente se o rompimento da resistencia sustentar na vela de 5 minutos com volume.",
            "Invalidar se voltar para baixo da resistencia rompida, perder VWAP/EMA21 ou devolver o volume.",
            "Risco medio: rompimento recente precisa de confirmacao de fluxo para aumentar tamanho.",
        )

    if close < support - buffer and close <= open_price and relative_volume >= 1.1:
        return _derived_trade_marker(
            ticker,
            "SHORT",
            marker_time,
            max(high_prices[index], close),
            "latest_support_breakdown",
            "Short somente se a perda do suporte sustentar na vela de 5 minutos com volume vendedor.",
            "Invalidar se recuperar o suporte perdido, voltar acima da VWAP/EMA21 ou absorver a venda.",
            "Risco medio: perda recente precisa de continuidade para evitar falso rompimento.",
        )

    return None


def _marker_series_index(marker: dict, series: list[dict]) -> int | None:
    marker_time = str(marker.get("time") or "")
    if not marker_time:
        return None
    for index, row in enumerate(series):
        if str(row.get("time") or "") == marker_time:
            return index
    return None


def _relative_volume_at(index: int, volume_values: list[float], lookback: int = 20) -> float:
    current = volume_values[index] if 0 <= index < len(volume_values) else 0.0
    previous = [value for value in volume_values[max(0, index - lookback) : index] if value > 0]
    if current <= 0 or not previous:
        return 1.0
    return current / max(sum(previous) / len(previous), 1.0)


def _future_outcome(index: int, close: float, close_prices: list[float], buffer: float, direction: str) -> bool:
    future_closes = close_prices[index + 1 : index + 7]
    if not future_closes:
        return False

    future_high = max(future_closes)
    future_low = min(future_closes)
    future_last = future_closes[-1]

    if direction == "buy":
        advance = future_high - close
        drawdown = close - future_low
        return advance >= buffer * 0.7 and future_last >= close + buffer * 0.15 and drawdown <= max(buffer * 1.4, advance * 0.85)

    if direction == "short":
        decline = close - future_low
        adverse = future_high - close
        return decline >= buffer * 0.7 and future_last <= close - buffer * 0.15 and adverse <= max(buffer * 1.4, decline * 0.85)

    if direction == "sell":
        return future_low <= close - buffer * 0.35 and future_last <= close + buffer * 0.05

    if direction == "cover":
        return future_high >= close + buffer * 0.35 and future_last >= close - buffer * 0.05

    return False


def _marker_is_coherent(marker: dict, ohlc: list, series: list[dict], high_prices: list[float], low_prices: list[float], close_prices: list[float], volume_values: list[float]) -> bool:
    event_type = str(marker.get("type") or "").upper()
    if event_type == "PRICE_EVENT":
        return True

    index = _marker_series_index(marker, series)
    if index is None or index <= 2 or index >= len(close_prices):
        return False

    close = close_prices[index]
    if close <= 0:
        return False

    try:
        open_price = float(ohlc[index].get("open", close) or close)
    except Exception:
        open_price = close

    ema9_value = series[index].get("ema9") or close
    ema21_value = series[index].get("ema21") or ema9_value
    ema50_value = series[index].get("ema50") or ema21_value
    trend_side = str(series[index].get("supertrend_side") or "neutral").lower()
    previous_highs = high_prices[max(0, index - 10) : index]
    previous_lows = low_prices[max(0, index - 10) : index]
    if not previous_highs or not previous_lows:
        return False

    resistance = max(previous_highs)
    support = min(previous_lows)
    band = max(resistance - support, abs(close) * 0.001, 0.0001)
    buffer = max(band * 0.015, abs(close) * 0.0004)
    rvol = _relative_volume_at(index, volume_values)
    momentum_3 = close - close_prices[max(0, index - 3)]
    bullish_candle = close >= open_price
    bearish_candle = close <= open_price
    breakout = close > resistance + buffer
    breakdown = close < support - buffer
    bullish_structure = close >= ema9_value and close >= ema21_value and (trend_side == "buy" or ema9_value >= ema21_value or breakout)
    bearish_structure = close <= ema9_value and close <= ema21_value and (trend_side == "sell" or ema9_value <= ema21_value or breakdown)

    bullish_break_confirmation = breakout or (close >= resistance - buffer * 0.25 and momentum_3 > 0 and rvol >= 1.05)
    bearish_break_confirmation = breakdown or (close <= support + buffer * 0.25 and momentum_3 < 0 and rvol >= 1.05)
    future_closes = close_prices[index + 1 : index + 7]
    bullish_follow_through = (
        _future_outcome(index, close, close_prices, buffer, "buy")
    )
    bearish_follow_through = (
        _future_outcome(index, close, close_prices, buffer, "short")
    )

    if event_type == "BUY":
        return bullish_candle and bullish_structure and bullish_break_confirmation and bullish_follow_through and rvol >= 1.08
    if event_type == "SHORT":
        return bearish_candle and bearish_structure and bearish_break_confirmation and bearish_follow_through and rvol >= 1.08
    if event_type == "SELL":
        return bearish_candle and _future_outcome(index, close, close_prices, buffer, "sell") and (close < ema9_value or close < ema21_value or breakdown or momentum_3 < 0)
    if event_type == "COVER":
        return bullish_candle and _future_outcome(index, close, close_prices, buffer, "cover") and (close > ema9_value or close > ema21_value or breakout or momentum_3 > 0)
    return False


def _filter_coherent_trade_markers(markers: list[dict], ohlc: list, series: list[dict], high_prices: list[float], low_prices: list[float], close_prices: list[float], volume_values: list[float]) -> list[dict]:
    coherent: list[dict] = []
    for marker in markers:
        if marker.get("explicit"):
            coherent.append(marker)
            continue
        if _marker_is_coherent(marker, ohlc, series, high_prices, low_prices, close_prices, volume_values):
            coherent.append(marker)
    return coherent


def _dedupe_trade_markers(markers: list[dict], series: list[dict]) -> list[dict]:
    sorted_markers = sorted(
        markers,
        key=lambda marker: next(
            (index for index, row in enumerate(series) if str(row.get("time") or "") == str(marker.get("time") or "")),
            len(series),
        ),
    )
    unique: list[dict] = []
    seen: set[tuple[str, str]] = set()
    used_side_by_time: dict[str, str] = {}
    for marker in sorted_markers:
        marker_type = str(marker.get("type") or "").upper()
        marker_time = str(marker.get("time") or "")
        if not marker_time:
            continue
        key = (marker_time, marker_type)
        if key in seen:
            continue
        side = _trade_side(marker_type)
        if side in {"buy", "sell"}:
            previous_side = used_side_by_time.get(marker_time)
            if previous_side and previous_side != side:
                continue
            used_side_by_time[marker_time] = side
        seen.add(key)
        unique.append(marker)
    return unique


def _count_marker_sides(markers: list[dict]) -> tuple[int, int]:
    bullish = 0
    bearish = 0
    for marker in markers:
        side = _trade_side(str(marker.get("type") or "").upper())
        if side == "buy":
            bullish += 1
        elif side == "sell":
            bearish += 1
    return bullish, bearish


def build_chart_overlays(ticker: str, ohlc: list, signals: list, interval: str = "1D"):
    ticker = (ticker or "").upper().strip()
    normalized_interval = str(interval or "1D").upper().strip()
    close_prices = [float(row.get("close", 0) or 0) for row in ohlc]
    high_prices = [float(row.get("high", 0) or 0) for row in ohlc]
    low_prices = [float(row.get("low", 0) or 0) for row in ohlc]
    volume_values = [float(row.get("volume", 0) or 0) for row in ohlc]

    ema9 = _ema(close_prices, 9)
    ema21 = _ema(close_prices, 21)
    ema50 = _ema(close_prices, 50)
    supertrend, supertrend_side = _supertrend(high_prices, low_prices, close_prices)

    series = []
    markers = []
    bullish_markers = 0
    bearish_markers = 0
    latest_signal = "NEUTRAL"

    for index, row in enumerate(ohlc):
        series.append(
            {
                "time": row.get("time"),
                "close": close_prices[index],
                "ema9": ema9[index] if index < len(ema9) else None,
                "ema21": ema21[index] if index < len(ema21) else None,
                "ema50": ema50[index] if index < len(ema50) else None,
                "supertrend": supertrend[index] if index < len(supertrend) else None,
                "supertrend_side": supertrend_side[index] if index < len(supertrend_side) else "neutral",
            }
        )

    for signal in signals or []:
        if signal.get("signal"):
            latest_signal = str(signal.get("signal") or latest_signal).upper()

        for event in signal.get("events", []):
            raw_event_type = str(event.get("type", "")).upper()

            if raw_event_type not in {"BUY", "SELL", "SHORT", "COVER", "PRICE_EVENT"}:
                continue

            event_type = _DISPLAY_EVENT_TYPE_MAP.get(raw_event_type, raw_event_type)
            side = _trade_side(event_type)
            shape, color = _trade_marker_style(event_type)

            if side == "buy":
                side = "buy"
                bullish_markers += 1
            elif side == "sell":
                side = "sell"
                bearish_markers += 1

            markers.append(
                {
                    "ticker": ticker,
                    "type": event_type,
                    "source_event_type": raw_event_type,
                    "explicit": True,
                    "side": side,
                    "shape": shape,
                    "color": color,
                    "label": _TRADE_LABELS.get(event_type, event_type.title()),
                    "action_label": _TRADE_LABELS.get(event_type, event_type.title()),
                    "operational_note": _TRADE_NOTES.get(event_type, event_type.title()),
                    "time": event.get("time"),
                    "price": event.get("price"),
                    "change": event.get("change"),
                    "score": event.get("score"),
                    "confidence": event.get("confidence"),
                    "reason": event.get("reason"),
                    "reason_text": event.get("reason_text"),
                    "trigger": event.get("trigger"),
                    "confirmation": event.get("confirmation"),
                    "invalidation": event.get("invalidation"),
                    "risk": event.get("risk"),
                    "risk_level": event.get("risk_level"),
                    "coherence_status": event.get("coherence_status"),
                    "chart_regime_state": event.get("chart_regime_state"),
                    "liquidity_event": event.get("liquidity_event"),
                }
            )

    markers = _filter_coherent_trade_markers(markers, ohlc, series, high_prices, low_prices, close_prices, volume_values)
    bullish_markers, bearish_markers = _count_marker_sides(markers)
    operational_marker_count = len([marker for marker in markers if str(marker.get("type") or "").upper() != "WATCH"])
    allow_derived_markers = operational_marker_count < 2
    derived_marker_limit = 2 if normalized_interval == "1D" else 2

    if allow_derived_markers and len(series) >= 12:
        average_volume = max(sum(volume_values) / max(len(volume_values), 1), 1.0)
        last_marker_index = -8
        for index in range(8, len(series)):
            if index - last_marker_index < 8:
                continue
            previous_highs = high_prices[max(0, index - 8) : index]
            previous_lows = low_prices[max(0, index - 8) : index]
            if not previous_highs or not previous_lows:
                continue
            close = close_prices[index]
            open_price = float(ohlc[index].get("open", close) or close)
            resistance = max(previous_highs)
            support = min(previous_lows)
            band = max(resistance - support, abs(close) * 0.001, 0.0001)
            buffer = max(band * 0.02, abs(close) * 0.0006)
            relative_volume = _relative_volume_at(index, volume_values)
            marker_time = series[index].get("time")
            ema9_value = series[index].get("ema9") or close
            ema21_value = series[index].get("ema21") or ema9_value
            bullish_alignment = close >= ema9_value >= ema21_value or (close >= ema9_value and series[index].get("supertrend_side") == "buy")
            bearish_alignment = close <= ema9_value <= ema21_value or (close <= ema9_value and series[index].get("supertrend_side") == "sell")

            bullish_follow_through = _future_outcome(index, close, close_prices, buffer, "buy")
            bearish_follow_through = _future_outcome(index, close, close_prices, buffer, "short")

            if close > resistance + buffer and close >= open_price and bullish_alignment and bullish_follow_through and relative_volume >= 1.1:
                markers.append(
                    _derived_trade_marker(
                        ticker,
                        "BUY",
                        marker_time,
                        low_prices[index],
                        "resistance_breakout",
                        "Comprar somente se a vela de 5 minutos fechar acima da resistencia com volume e sem devolucao imediata.",
                        "Invalidar se voltar para baixo da resistencia rompida ou perder VWAP/EMA21.",
                        "Risco medio: rompimento derivado exige confirmacao de fluxo antes de aumentar tamanho.",
                    )
                )
                latest_signal = "BUY"
                bullish_markers += 1
                last_marker_index = index
            elif close < support - buffer and close <= open_price and bearish_alignment and bearish_follow_through and relative_volume >= 1.1:
                markers.append(
                    _derived_trade_marker(
                        ticker,
                        "SHORT",
                        marker_time,
                        high_prices[index],
                        "support_breakdown",
                        "Abrir short somente se a vela de 5 minutos fechar abaixo do suporte com volume e continuidade vendedora.",
                        "Invalidar se recuperar o suporte perdido ou voltar acima da VWAP/EMA21.",
                        "Risco medio: perda de suporte derivada exige confirmacao de fluxo antes de aumentar tamanho.",
                    )
                )
                latest_signal = "SHORT"
                bearish_markers += 1
                last_marker_index = index

            if len([marker for marker in markers if str(marker.get("type") or "").upper() != "WATCH"]) >= derived_marker_limit:
                break

    latest_structure_marker = _latest_structure_trade_marker(
        ticker,
        ohlc,
        series,
        high_prices,
        low_prices,
        close_prices,
        volume_values,
    )
    if latest_structure_marker:
        latest_time = str(latest_structure_marker.get("time") or "")
        latest_type = str(latest_structure_marker.get("type") or "").upper()
        opposite_types = {"SHORT", "COVER"} if latest_type == "BUY" else {"BUY", "SELL"}
        has_same_marker = any(
            str(marker.get("time") or "") == latest_time and str(marker.get("type") or "").upper() == latest_type
            for marker in markers
        )
        if not has_same_marker:
            markers = [
                marker
                for marker in markers
                if not (
                    str(marker.get("time") or "") == latest_time
                    and str(marker.get("type") or "").upper() in opposite_types
                )
            ]
            markers.append(latest_structure_marker)
            latest_signal = latest_type
            if _trade_side(latest_type) == "buy":
                bullish_markers += 1
            elif _trade_side(latest_type) == "sell":
                bearish_markers += 1

    markers = _dedupe_trade_markers(markers, series)[-5:]
    bullish_markers, bearish_markers = _count_marker_sides(markers)
    actionable_markers = [marker for marker in markers if str(marker.get("type") or "").upper() not in {"WATCH", "PRICE_EVENT"}]
    if actionable_markers:
        latest_signal = str(actionable_markers[-1].get("type") or latest_signal).upper()

    recent_high = max(high_prices[-20:], default=0)
    recent_low = min(low_prices[-20:], default=0)

    zones = [
        {"label": "resistencia", "price": recent_high},
        {"label": "suporte", "price": recent_low},
    ]

    summary = {
        "ticker": ticker,
        "latest_close": close_prices[-1] if close_prices else None,
        "trend_bias": (
            "alta"
            if ema9 and ema21 and ema50 and ema9[-1] >= ema21[-1] >= ema50[-1]
            else "baixa"
        ),
        "latest_signal": latest_signal,
        "bullish_markers": bullish_markers,
        "bearish_markers": bearish_markers,
        "markers": len(markers),
    }

    return {
        "series": series,
        "markers": markers,
        "zones": zones,
        "summary": summary,
    }
