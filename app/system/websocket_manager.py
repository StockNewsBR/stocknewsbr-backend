# =====================================================
# WEBSOCKET CONNECTION MANAGER
# Fast + Crash Safe
# =====================================================

import logging
import asyncio
import threading

from typing import List
from fastapi import WebSocket

from app.system.system_metrics import decrement_ws_connections, increment_ws_connections


logger = logging.getLogger("stocknewsbr.websocket_manager")


class ConnectionManager:

    def __init__(self):

        self._connections: List[WebSocket] = []

        self._lock = threading.RLock()

    # --------------------------------------------------
    # CONNECT
    # --------------------------------------------------

    async def connect(self, websocket: WebSocket):

        await websocket.accept()

        with self._lock:

            self._connections.append(websocket)

        logger.info("WebSocket client connected")
        increment_ws_connections()

    # --------------------------------------------------
    # DISCONNECT
    # --------------------------------------------------

    def disconnect(self, websocket: WebSocket):

        with self._lock:

            if websocket in self._connections:

                self._connections.remove(websocket)

        logger.info("WebSocket client disconnected")
        decrement_ws_connections()

    # --------------------------------------------------
    # BROADCAST
    # --------------------------------------------------

    async def broadcast(self, message):

        with self._lock:

            connections = list(self._connections)

        if not connections:
            return

        tasks = []

        for connection in connections:

            tasks.append(self._safe_send(connection, message))

        await asyncio.gather(*tasks, return_exceptions=True)

    # --------------------------------------------------
    # SAFE SEND
    # --------------------------------------------------

    async def _safe_send(self, websocket: WebSocket, message):

        try:

            await websocket.send_json(message)

        except Exception as e:

            logger.warning(f"WebSocket send error: {e}")

            self.disconnect(websocket)


# =====================================================
# GLOBAL INSTANCE
# =====================================================

manager = ConnectionManager()
