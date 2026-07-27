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


def _build_series(
    ohlc: list, close_prices: list, ema9: list, ema21: list, ema50: list
) -> list:
    series = []
    for index, row in enumerate(ohlc):
        series.append(
            {
                "time": row.get("time"),
                "close": close_prices[index],
                "ema9": ema9[index] if index < len(ema9) else None,
                "ema21": ema21[index] if index < len(ema21) else None,
                "ema50": ema50[index] if index < len(ema50) else None,
            }
        )
    return series


def _process_signals(ticker: str, signals: list) -> tuple:
    markers = []
    bullish_markers = 0
    bearish_markers = 0
    latest_signal = "NEUTRAL"

    for signal in signals or []:
        if signal.get("signal"):
            latest_signal = str(signal.get("signal") or latest_signal).upper()

        for event in signal.get("events", []):
            event_type = str(event.get("type", "")).upper()

            if event_type not in {"BUY", "SELL", "SHORT", "COVER", "PRICE_EVENT"}:
                continue

            side = "neutral"
            shape = "circle"
            color = "gray"

            if event_type in {"BUY", "COVER"}:
                side = "buy"
                bullish_markers += 1
            elif event_type in {"SELL", "SHORT"}:
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
                    "label": event_type.title(),
                    "time": event.get("time"),
                    "price": event.get("price"),
                    "change": event.get("change"),
                    "score": event.get("score"),
                    "reason": event.get("reason"),
                }
            )

    return markers, bullish_markers, bearish_markers, latest_signal


def _build_zones(high_prices: list, low_prices: list) -> list:
    recent_high = max(high_prices[-20:], default=0)
    recent_low = min(low_prices[-20:], default=0)

    return [
        {"label": "resistencia", "price": recent_high},
        {"label": "suporte", "price": recent_low},
    ]


def _build_summary(
    ticker: str,
    close_prices: list,
    ema9: list,
    ema21: list,
    ema50: list,
    latest_signal: str,
    bullish_markers: int,
    bearish_markers: int,
    markers_len: int,
) -> dict:
    return {
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
        "markers": markers_len,
    }


def build_chart_overlays(ticker: str, ohlc: list, signals: list):
    ticker = (ticker or "").upper().strip()
    close_prices = [float(row.get("close", 0) or 0) for row in ohlc]
    high_prices = [float(row.get("high", 0) or 0) for row in ohlc]
    low_prices = [float(row.get("low", 0) or 0) for row in ohlc]

    ema9 = _ema(close_prices, 9)
    ema21 = _ema(close_prices, 21)
    ema50 = _ema(close_prices, 50)

    series = _build_series(ohlc, close_prices, ema9, ema21, ema50)
    markers, bullish_markers, bearish_markers, latest_signal = _process_signals(
        ticker, signals
    )
    zones = _build_zones(high_prices, low_prices)
    summary = _build_summary(
        ticker,
        close_prices,
        ema9,
        ema21,
        ema50,
        latest_signal,
        bullish_markers,
        bearish_markers,
        len(markers),
    )

    return {
        "series": series,
        "markers": markers,
        "zones": zones,
        "summary": summary,
    }
