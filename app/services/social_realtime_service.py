from app.system.room_websocket_manager import room_ws_manager


async def broadcast_ticker_event(symbol: str | None, event_type: str, payload: dict):
    symbol = (symbol or "").upper().strip()

    if not symbol:
        return

    await room_ws_manager.broadcast(
        symbol,
        {
            "type": event_type,
            "symbol": symbol,
            **payload,
        },
    )
