from app.engine.trend_breakout_signal_engine import (
    build_trend_breakout_payload,
    resolve_chart_timeframe,
)
from app.market.market_data_loader import get_ticker_frame


def _frame_to_ohlc(frame):
    rows = []

    if frame is None or frame.empty:
        return rows

    # Use tail(240) to match original signal_engine.py logic
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


def build_chart_signal_payload(symbol: str, ohlc, interval: str = "1D"):
    """Build chart signal payload using trend breakout engine.

    This function was moved from signal_engine.py (now deleted).
    """
    return build_trend_breakout_payload(
        symbol,
        ohlc,
        timeframe=resolve_chart_timeframe(interval),
        ai_context={},  # ai_context is optional in trend_breakout_signal_engine
    )


def generate_signals(symbol: str):
    """Generate signals for a symbol.

    This function was moved from signal_engine.py (now deleted).
    """
    frame = get_ticker_frame(symbol, period="1mo", interval="5m")

    if frame is None or frame.empty:
        return []

    ohlc = _frame_to_ohlc(frame)
    payload = build_chart_signal_payload(symbol, ohlc, interval="5m")

    if not payload:
        return []

    return payload.get("events", [])


def chart_signals(symbol):
    signals = generate_signals(symbol)
    chart_events = []

    for s in signals:
        event_type = str(s.get("type", "")).upper()
        shape = "circle"
        color = "gray"

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
        else:
            continue

        chart_events.append(
            {
                "type": event_type.lower(),
                "shape": shape,
                "color": color,
                "price": s.get("price"),
                "time": s.get("time"),
                "score": s.get("score"),
                "reason": s.get("reason"),
            }
        )

    return chart_events
