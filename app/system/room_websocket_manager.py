# =====================================================
# ROOM WEBSOCKET MANAGER
# Mission 31F: per-room + global capacity reservation,
# accept timeout, duplicate rejection and idempotent
# disconnect.
# =====================================================

import asyncio
import inspect
import logging
import threading

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from fastapi import WebSocket

from app.system.system_metrics import decrement_ws_connections, increment_ws_connections


logger = logging.getLogger("stocknewsbr.room_ws_manager")

# Patchable at module level (tests patch app.system.room_websocket_manager.ACCEPT_TIMEOUT_SECONDS).
ACCEPT_TIMEOUT_SECONDS = 10.0

_DUPLICATE_IDENTITY_ATTRIBUTES = (
    "connection_id",
    "client_id",
    "session_id",
    "websocket_id",
    "ws_id",
    "name",
    "key",
)


def _connection_fingerprint(websocket: Any) -> Optional[Tuple[str, Any]]:
    """Best-effort stable identity for duplicate detection (same rules as
    app.system.websocket_manager)."""
    for attribute in _DUPLICATE_IDENTITY_ATTRIBUTES:
        try:
            value = getattr(websocket, attribute, None)
        except Exception:
            value = None
        if value is not None:
            return (attribute, value)
    try:
        headers = getattr(websocket, "headers", None)
        if headers is not None:
            ws_key = headers.get("sec-websocket-key")
            if ws_key:
                return ("sec-websocket-key", ws_key)
    except Exception:
        pass
    return None


def _is_same_connection(candidate: Any, registered: Any) -> bool:
    if candidate is registered:
        return True
    candidate_fp = _connection_fingerprint(candidate)
    if candidate_fp is None:
        return False
    return candidate_fp == _connection_fingerprint(registered)


async def _close_websocket(websocket: Any, code: int, reason: Optional[str] = None) -> None:
    close = getattr(websocket, "close", None)
    if close is None:
        return
    try:
        result = close(code=code, reason=reason)
        if inspect.isawaitable(result):
            await result
    except TypeError:
        try:
            result = close()
            if inspect.isawaitable(result):
                await result
        except Exception:
            pass
    except Exception:
        pass


def _normalize_room(room: Any) -> str:
    return str(room or "").upper()


class RoomWebSocketManager:
    def __init__(self):
        self._rooms: Dict[str, List[Any]] = defaultdict(list)
        self._pending_websockets: Dict[str, List[Any]] = defaultdict(list)
        self._max_connections = 1000
        self._max_connections_per_room = 100
        self._lock = threading.RLock()

    # --------------------------------------------------
    # CONNECT
    # --------------------------------------------------

    async def connect(self, room: str, websocket: WebSocket) -> bool:
        room_key = _normalize_room(room)

        with self._lock:
            duplicate = self._find_duplicate_locked(room_key, websocket)
            if duplicate is not None:
                self._purge_locked(room_key, duplicate)
                capacity_available = False
            else:
                room_count = len(self._rooms.get(room_key, ())) + len(
                    self._pending_websockets.get(room_key, ())
                )
                total_count = self._total_locked() + self._total_pending_locked()
                if room_count >= self._room_limit():
                    capacity_available = False
                elif total_count >= self._global_limit():
                    capacity_available = False
                else:
                    capacity_available = True
                    # Reserve a slot while accept() is in flight.
                    self._pending_websockets[room_key].append(websocket)
            self._cleanup_room_locked(room_key)

        if duplicate is not None:
            logger.warning("Duplicate room WebSocket connection rejected (room=%s)", room_key)
            await _close_websocket(websocket, 1011, "duplicate_connection")
            return False

        if not capacity_available:
            logger.warning("Room WebSocket connection rejected: capacity reached (room=%s)", room_key)
            await _close_websocket(websocket, 1013, "capacity_reached")
            return False

        try:
            await asyncio.wait_for(websocket.accept(), timeout=ACCEPT_TIMEOUT_SECONDS)
        except Exception as exc:
            with self._lock:
                self._release_pending_locked(room_key, websocket)
                self._cleanup_room_locked(room_key)
            logger.warning("Room WebSocket accept failed or timed out (room=%s): %s", room_key, exc)
            await _close_websocket(websocket, 1013, "accept_failed")
            return False

        with self._lock:
            self._release_pending_locked(room_key, websocket)
            self._rooms[room_key].append(websocket)

        increment_ws_connections()
        return True

    def _room_limit(self) -> int:
        try:
            return int(self._max_connections_per_room)
        except Exception:
            return 100

    def _global_limit(self) -> int:
        try:
            return int(self._max_connections)
        except Exception:
            return 1000

    def _total_locked(self) -> int:
        return sum(len(items) for items in self._rooms.values())

    def _total_pending_locked(self) -> int:
        return sum(len(items) for items in self._pending_websockets.values())

    def _find_duplicate_locked(self, room_key: str, websocket: Any) -> Optional[Any]:
        registered = list(self._rooms.get(room_key, ())) + list(
            self._pending_websockets.get(room_key, ())
        )
        for candidate in registered:
            if _is_same_connection(websocket, candidate):
                return candidate
        return None

    def _release_pending_locked(self, room_key: str, websocket: Any) -> None:
        pending = self._pending_websockets.get(room_key)
        if pending and websocket in pending:
            pending.remove(websocket)

    def _purge_locked(self, room_key: str, websocket: Any) -> None:
        removed = False
        connections = self._rooms.get(room_key)
        if connections is not None:
            while websocket in connections:
                connections.remove(websocket)
                removed = True
        if removed:
            decrement_ws_connections()
        self._release_pending_locked(room_key, websocket)

    def _cleanup_room_locked(self, room_key: str) -> None:
        if room_key in self._rooms and not self._rooms[room_key]:
            self._rooms.pop(room_key, None)
        if room_key in self._pending_websockets and not self._pending_websockets[room_key]:
            self._pending_websockets.pop(room_key, None)

    # --------------------------------------------------
    # DISCONNECT (idempotent)
    # --------------------------------------------------

    def disconnect(self, room: str, websocket: WebSocket) -> None:
        room_key = _normalize_room(room)
        removed = False
        with self._lock:
            connections = self._rooms.get(room_key)
            if connections is not None:
                while websocket in connections:
                    connections.remove(websocket)
                    removed = True
            self._release_pending_locked(room_key, websocket)
            self._cleanup_room_locked(room_key)

        if removed:
            decrement_ws_connections()

    # --------------------------------------------------
    # BROADCAST
    # --------------------------------------------------

    async def broadcast(self, room: str, message: dict):
        room_key = _normalize_room(room)
        with self._lock:
            connections = list(self._rooms.get(room_key, ()))

        if not connections:
            return

        await asyncio.gather(
            *[self._safe_send(room_key, websocket, message) for websocket in connections],
            return_exceptions=True,
        )

    async def _safe_send(self, room: str, websocket: WebSocket, message: dict):
        try:
            await websocket.send_json(message)
        except Exception as exc:
            logger.warning("Room websocket send failed: %s", exc)
            self.disconnect(room, websocket)

    # --------------------------------------------------
    # STATS
    # --------------------------------------------------

    def stats(self, room: Optional[str] = None) -> dict:
        with self._lock:
            rooms_view = {key: len(items) for key, items in self._rooms.items() if len(items) > 0}
            total = sum(rooms_view.values())
            total_pending = self._total_pending_locked()
            if room is None:
                room_key = None
                active = total
                pending = total_pending
            else:
                room_key = _normalize_room(room)
                active = len(self._rooms.get(room_key, ()))
                pending = len(self._pending_websockets.get(room_key, ()))
        return {
            "room": room_key,
            "active": active,
            "connections": active,
            "total": total,
            "limit": self._global_limit(),
            "limit_per_room": self._room_limit(),
            "pending_accepts": pending,
            "rooms": rooms_view,
        }


room_ws_manager = RoomWebSocketManager()
