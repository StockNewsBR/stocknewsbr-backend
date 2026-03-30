import asyncio
import logging
import threading
from collections import defaultdict

from fastapi import WebSocket

from app.system.system_metrics import decrement_ws_connections, increment_ws_connections


logger = logging.getLogger("stocknewsbr.room_ws_manager")


class RoomWebSocketManager:
    def __init__(self):
        self._rooms = defaultdict(list)
        self._lock = threading.RLock()

    async def connect(self, room: str, websocket: WebSocket):
        await websocket.accept()

        with self._lock:
            self._rooms[room].append(websocket)

        increment_ws_connections()

    def disconnect(self, room: str, websocket: WebSocket):
        with self._lock:
            connections = self._rooms.get(room, [])
            if websocket in connections:
                connections.remove(websocket)

            if not connections and room in self._rooms:
                self._rooms.pop(room, None)

        decrement_ws_connections()

    async def broadcast(self, room: str, message: dict):
        with self._lock:
            connections = list(self._rooms.get(room, []))

        if not connections:
            return

        await asyncio.gather(
            *[self._safe_send(room, websocket, message) for websocket in connections],
            return_exceptions=True,
        )

    async def _safe_send(self, room: str, websocket: WebSocket, message: dict):
        try:
            await websocket.send_json(message)
        except Exception as exc:
            logger.warning("Room websocket send failed: %s", exc)
            self.disconnect(room, websocket)


room_ws_manager = RoomWebSocketManager()
