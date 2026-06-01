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
    "BUY": "Buy",
    "SELL": "Partial Sell",
    "SHORT": "Short",
    "COVER": "Cover Short",
    "PRICE_EVENT": "Evento",
}


_TRADE_NOTES = {
    "BUY": "Entrada compra",
    "SELL": "Venda parcial",
    "SHORT": "Entrada short",
    "COVER": "Encerrar short",
    "PRICE_EVENT": "Evento de preco",
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

            event_type = raw_event_type
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

    operational_marker_count = len(markers)
    allow_derived_markers = operational_marker_count == 0
    derived_marker_limit = 3 if normalized_interval == "1D" else 4

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
            relative_volume = volume_values[index] / average_volume if average_volume > 0 else 1.0
            marker_time = series[index].get("time")

            if close > resistance + buffer and close >= open_price and relative_volume >= 0.75:
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
            elif close < support - buffer and close <= open_price and relative_volume >= 0.75:
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

            if len(markers) >= derived_marker_limit:
                break

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
