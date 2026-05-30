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


def _trade_side(event_type: str):
    if event_type in {"BUY", "COVER"}:
        return "buy"
    if event_type in {"SELL", "SHORT"}:
        return "sell"
    return "neutral"


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


def build_chart_overlays(ticker: str, ohlc: list, signals: list, interval: str = "1D"):
    ticker = (ticker or "").upper().strip()
    normalized_interval = str(interval or "1D").upper().strip()
    close_prices = [float(row.get("close", 0) or 0) for row in ohlc]
    high_prices = [float(row.get("high", 0) or 0) for row in ohlc]
    low_prices = [float(row.get("low", 0) or 0) for row in ohlc]

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
            event_type = str(event.get("type", "")).upper()

            if event_type not in {"BUY", "SELL", "SHORT", "COVER", "PRICE_EVENT"}:
                continue

            side = _trade_side(event_type)
            shape = "circle"
            color = "gray"

            if side == "buy":
                side = "buy"
                bullish_markers += 1
            elif side == "sell":
                side = "sell"
                bearish_markers += 1

            if event_type == "BUY":
                shape = "circle"
                color = "green"
            elif event_type == "SELL":
                shape = "circle"
                color = "red"
            elif event_type == "SHORT":
                shape = "square"
                color = "orange"
            elif event_type == "COVER":
                shape = "diamond"
                color = "blue"

            markers.append(
                {
                    "ticker": ticker,
                    "type": event_type,
                    "side": side,
                    "shape": shape,
                    "color": color,
                    "label": event.get("action_label") or event.get("label") or _TRADE_LABELS.get(event_type, event_type.title()),
                    "action_label": event.get("action_label") or event.get("label") or _TRADE_LABELS.get(event_type, event_type.title()),
                    "operational_note": event.get("operational_note") or _TRADE_NOTES.get(event_type, event_type.title()),
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

    operational_marker_count = len(markers)
    allow_derived_markers = operational_marker_count == 0
    derived_marker_limit = 3 if normalized_interval == "1D" else 4

    cross_min_bars = 10 if normalized_interval == "1D" else 24
    cross_spacing = max(3, len(series) // 24) if normalized_interval == "1D" else max(8, len(series) // 18)
    if allow_derived_markers and len(markers) < derived_marker_limit and len(series) >= cross_min_bars:
        last_side = None
        min_spacing = cross_spacing
        existing_times = {str(marker.get("time") or "") for marker in markers}
        last_marker_index = -min_spacing

        for index in range(1, len(series)):
            if index - last_marker_index < min_spacing:
                continue

            previous_fast = ema9[index - 1] if index - 1 < len(ema9) else None
            previous_slow = ema21[index - 1] if index - 1 < len(ema21) else None
            current_fast = ema9[index] if index < len(ema9) else None
            current_slow = ema21[index] if index < len(ema21) else None

            if previous_fast is None or previous_slow is None or current_fast is None or current_slow is None:
                continue

            side = None
            event_type = None
            if previous_fast <= previous_slow and current_fast > current_slow and last_side != "buy":
                side = "buy"
                event_type = "BUY"
            elif previous_fast >= previous_slow and current_fast < current_slow and last_side != "sell":
                side = "sell"
                event_type = "SELL"

            if not side or not event_type:
                continue
            if str(series[index].get("time") or "") in existing_times:
                continue

            markers.append(
                _derived_watch_marker(
                    ticker,
                    event_type,
                    series[index].get("time"),
                    close_prices[index],
                    round(abs(ema9[index] - ema21[index]) / max(close_prices[index], 0.01) * 1000, 1),
                    "ema9_ema21_cross",
                    "Cruzamento de medias detectado; operar apenas se regime, volume e fluxo confirmarem o mesmo lado.",
                    "Ignorar se o cruzamento falhar, perder a media curta ou aparecer conflito de liquidez/fluxo.",
                    "Risco medio: cruzamento em mercado lateral gera falso sinal com frequencia.",
                )
            )
            latest_signal = "WATCH"
            last_side = side
            last_marker_index = index
            existing_times.add(str(series[index].get("time") or ""))
            if len(markers) >= derived_marker_limit:
                break

        markers = markers[-8:]

    pivot_min_bars = 12 if normalized_interval == "1D" else 30
    pivot_spacing = max(4, len(series) // 10) if normalized_interval == "1D" else max(8, len(series) // 12)
    pivot_window = 2 if normalized_interval == "1D" else 3
    if allow_derived_markers and len(markers) < derived_marker_limit and len(series) >= pivot_min_bars:
        existing_times = {str(marker.get("time") or "") for marker in markers}
        min_spacing = pivot_spacing
        last_marker_index = -min_spacing
        window = pivot_window

        for index in range(window, len(series) - window):
            if index - last_marker_index < min_spacing:
                continue
            marker_time = str(series[index].get("time") or "")
            if marker_time in existing_times:
                continue

            neighborhood_lows = low_prices[index - window : index + window + 1]
            neighborhood_highs = high_prices[index - window : index + window + 1]
            is_swing_low = low_prices[index] <= min(neighborhood_lows)
            is_swing_high = high_prices[index] >= max(neighborhood_highs)

            if not is_swing_low and not is_swing_high:
                continue

            side = "buy" if is_swing_low else "sell"
            event_type = "BUY" if is_swing_low else "SELL"

            marker_price = low_prices[index] if side == "buy" else high_prices[index]
            markers.append(
                _derived_watch_marker(
                    ticker,
                    event_type,
                    series[index].get("time"),
                    marker_price,
                    round(abs(close_prices[index] - ema21[index]) / max(close_prices[index], 0.01) * 1000, 1),
                    "swing_pivot",
                    "Pivo tecnico detectado; aguardar reacao com volume e alinhamento com tendencia/regime.",
                    "Ignorar se o pivo romper sem defesa ou se o fluxo institucional apontar lado contrario.",
                    "Risco medio: pivo derivado pode falhar em mercado lateral ou sem liquidez.",
                )
            )
            latest_signal = "WATCH"
            last_marker_index = index
            existing_times.add(marker_time)
            if len(markers) >= derived_marker_limit:
                break

        markers = markers[-8:]

    existing_times = {str(marker.get("time") or "") for marker in markers}
    if allow_derived_markers and len(markers) < derived_marker_limit:
        for index in range(1, len(series)):
            previous_side = supertrend_side[index - 1] if index - 1 < len(supertrend_side) else "neutral"
            current_side = supertrend_side[index] if index < len(supertrend_side) else "neutral"
            if current_side == previous_side or current_side not in {"buy", "sell"}:
                continue
            marker_time = str(series[index].get("time") or "")
            if marker_time in existing_times:
                continue
            if len(markers) >= derived_marker_limit:
                break
            event_type = "BUY" if current_side == "buy" else "SELL"
            markers.append(
                _derived_watch_marker(
                    ticker,
                    event_type,
                    series[index].get("time"),
                    close_prices[index],
                    round(abs(close_prices[index] - (supertrend[index] or close_prices[index])), 2),
                    "supertrend_flip",
                    "Virada de supertrend detectada; aguardar volume e ausencia de conflito de regime.",
                    "Ignorar se o preco voltar contra a linha do supertrend ou se smart money/regime divergirem.",
                    "Risco medio: flip tecnico derivado exige confirmacao de fluxo antes de virar trade.",
                )
            )
            latest_signal = "WATCH"
            existing_times.add(marker_time)

    markers = sorted(
        markers,
        key=lambda marker: next(
            (index for index, row in enumerate(series) if str(row.get("time") or "") == str(marker.get("time") or "")),
            len(series),
        ),
    )[-16:]

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
