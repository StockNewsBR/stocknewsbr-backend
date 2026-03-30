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


def build_chart_overlays(ticker: str, ohlc: list, signals: list):
    ticker = (ticker or "").upper().strip()
    close_prices = [float(row.get("close", 0) or 0) for row in ohlc]
    high_prices = [float(row.get("high", 0) or 0) for row in ohlc]
    low_prices = [float(row.get("low", 0) or 0) for row in ohlc]

    ema9 = _ema(close_prices, 9)
    ema21 = _ema(close_prices, 21)
    ema50 = _ema(close_prices, 50)

    series = []
    markers = []

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

    for signal in signals or []:
        for event in signal.get("events", []):
            event_type = str(event.get("type", "")).upper()

            if event_type not in {"BUY", "SELL", "SHORT", "COVER", "PRICE_EVENT"}:
                continue

            side = "neutral"

            if event_type in {"BUY", "COVER"}:
                side = "buy"
            elif event_type in {"SELL", "SHORT"}:
                side = "sell"

            markers.append(
                {
                    "ticker": ticker,
                    "type": event_type,
                    "side": side,
                    "time": event.get("time"),
                    "price": event.get("price"),
                    "change": event.get("change"),
                }
            )

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
            if ema9 and ema21 and ema9[-1] >= ema21[-1]
            else "baixa"
        ),
        "markers": len(markers),
    }

    return {
        "series": series,
        "markers": markers,
        "zones": zones,
        "summary": summary,
    }
