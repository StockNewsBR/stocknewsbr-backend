# =====================================================
# MARKET STREAM ROUTER
# Fast + Crash Safe
# =====================================================

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.system.websocket_manager import manager


logger = logging.getLogger("stocknewsbr.stream_router")


router = APIRouter()


# =====================================================
# WEBSOCKET ENDPOINT
# =====================================================

@router.websocket("/ws/market")

async def market_stream(websocket: WebSocket):

    await manager.connect(websocket)

    logger.info("WebSocket client connected")

    try:

        while True:

            try:

                # keep connection alive
                await websocket.receive_text()

            except WebSocketDisconnect:

                break

            except Exception as e:

                logger.warning(f"WebSocket message error: {e}")

                break

    finally:

        try:

            manager.disconnect(websocket)

        except Exception:

            pass

        logger.info("WebSocket client disconnected")