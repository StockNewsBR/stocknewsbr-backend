from app.ai.signal_engine import calculate_signal
from app.market.market_data_loader import get_ticker_frame


def generate_signals(symbol: str):
    frame = get_ticker_frame(symbol, period="5d", interval="30m")

    if frame is None or frame.empty:
        return []

    result = calculate_signal(symbol, frame)

    if not result:
        return []

    last_row = frame.iloc[-1]
    event_time = str(frame.index[-1])
    price = float(last_row.get("Close", 0) or 0)
    events = []

    if result.get("momentum", 0) > 0:
        events.append({"type": "BUY", "price": price, "time": event_time})

    if result.get("momentum", 0) < 0:
        events.append({"type": "SELL", "price": price, "time": event_time})

    if result.get("liquidity_sweep"):
        events.append({"type": "SHORT", "price": price, "time": event_time})

    if result.get("smart_money"):
        events.append({"type": "COVER", "price": price, "time": event_time})

    return events
