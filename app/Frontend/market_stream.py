# =====================================================
# STOCKNEWSBR MARKET WEBSOCKET STREAM
# Fast + Crash Safe
# =====================================================

import asyncio
import json
import logging
import threading

from fastapi import WebSocket, WebSocketDisconnect

from app.cache.market_snapshot_cache import get_snapshot


logger = logging.getLogger("stocknewsbr.websocket")

# =====================================================
# CONNECTIONS
# =====================================================

connections = set()

_connections_lock = threading.Lock()

STREAM_INTERVAL = 2


# =====================================================
# WEBSOCKET ENDPOINT
# =====================================================

async def websocket_endpoint(websocket: WebSocket):

    await websocket.accept()

    with _connections_lock:
        connections.add(websocket)

    logger.info("WebSocket client connected")

    try:

        while True:

            snapshot = get_snapshot()

            if snapshot is None:
                snapshot = []

            payload = json.dumps(snapshot)

            await websocket.send_text(payload)

            await asyncio.sleep(STREAM_INTERVAL)

    except WebSocketDisconnect:

        logger.info("WebSocket client disconnected")

    except Exception as e:

        logger.warning(f"WebSocket error: {e}")

    finally:

        with _connections_lock:

            if websocket in connections:
                connections.remove(websocket)