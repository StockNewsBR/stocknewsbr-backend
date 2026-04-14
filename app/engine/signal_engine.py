from app.market.market_data_loader import get_ticker_frame
from app.engine.trend_breakout_signal_engine import build_trend_breakout_payload


def _frame_to_ohlc(frame):
    rows = []

    if frame is None or frame.empty:
        return rows

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


def generate_signal_payload(
    symbol: str,
    period: str = "1mo",
    interval: str = "5m",
):
    frame = get_ticker_frame(symbol, period=period, interval=interval)

    if frame is None or frame.empty:
        return None

    ohlc = _frame_to_ohlc(frame)
    return build_trend_breakout_payload(symbol, ohlc, timeframe=interval)


def generate_signals(symbol: str):
    payload = generate_signal_payload(symbol, period="1mo", interval="5m")

    if not payload:
        return []

    return payload.get("events", [])
