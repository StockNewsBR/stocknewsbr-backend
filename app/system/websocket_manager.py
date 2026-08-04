# =====================================================
# WEBSOCKET CONNECTION MANAGER
# Fast + Crash Safe
# Mission 31F: capacity reservation, accept timeout,
# duplicate rejection and dead-client cleanup.
# =====================================================

import asyncio
import inspect
import logging
import threading

from typing import Any, List, Optional, Tuple

from fastapi import WebSocket

from app.system.system_metrics import decrement_ws_connections, increment_ws_connections


logger = logging.getLogger("stocknewsbr.websocket_manager")

# Patchable at module level (tests patch app.system.websocket_manager.ACCEPT_TIMEOUT_SECONDS).
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
    """Best-effort stable identity for duplicate detection.

    Works with real WebSocket objects and with test fakes that expose
    common identity attributes. Returns None when no stable attribute
    is available (identity comparison is used instead).
    """
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


class ConnectionManager:

    def __init__(self):
        self._connections: List[WebSocket] = []
        self._pending_websockets: List[Any] = []
        self._pending_accepts = 0
        self._max_connections = 1000
        self._lock = threading.RLock()

    # --------------------------------------------------
    # CONNECT
    # --------------------------------------------------

    async def connect(self, websocket: WebSocket) -> bool:
        with self._lock:
            duplicate = self._find_duplicate(websocket)
            if duplicate is not None:
                self._purge_locked(duplicate)
            elif len(self._connections) + self._pending_accepts >= self._limit():
                capacity_available = False
            else:
                capacity_available = True

            if duplicate is None and capacity_available:
                # Reserve a slot while accept() is in flight so concurrent
                # connects cannot oversubscribe capacity.
                self._pending_accepts += 1
                self._pending_websockets.append(websocket)

        if duplicate is not None:
            logger.warning("Duplicate WebSocket connection rejected")
            await _close_websocket(websocket, 1011, "duplicate_connection")
            return False

        if not capacity_available:
            logger.warning("WebSocket connection rejected: capacity reached")
            await _close_websocket(websocket, 1013, "capacity_reached")
            return False

        try:
            await asyncio.wait_for(websocket.accept(), timeout=ACCEPT_TIMEOUT_SECONDS)
        except Exception as exc:
            with self._lock:
                self._release_pending_locked(websocket)
            logger.warning("WebSocket accept failed or timed out: %s", exc)
            await _close_websocket(websocket, 1013, "accept_failed")
            return False

        with self._lock:
            self._release_pending_locked(websocket)
            self._connections.append(websocket)

        logger.info("WebSocket client connected")
        increment_ws_connections()
        return True

    def _limit(self) -> int:
        try:
            return int(self._max_connections)
        except Exception:
            return 1000

    def _find_duplicate(self, websocket: Any) -> Optional[Any]:
        for registered in self._connections + self._pending_websockets:
            if _is_same_connection(websocket, registered):
                return registered
        return None

    def _release_pending_locked(self, websocket: Any) -> None:
        if websocket in self._pending_websockets:
            self._pending_websockets.remove(websocket)
            if self._pending_accepts > 0:
                self._pending_accepts -= 1

    def _purge_locked(self, websocket: Any) -> None:
        removed = False
        while websocket in self._connections:
            self._connections.remove(websocket)
            removed = True
        if removed:
            decrement_ws_connections()
        self._release_pending_locked(websocket)

    # --------------------------------------------------
    # DISCONNECT (idempotent)
    # --------------------------------------------------

    def disconnect(self, websocket: WebSocket) -> None:
        removed = False
        with self._lock:
            while websocket in self._connections:
                self._connections.remove(websocket)
                removed = True
            self._release_pending_locked(websocket)

        if removed:
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

        tasks = [self._safe_send(connection, message) for connection in connections]
        await asyncio.gather(*tasks, return_exceptions=True)

    # --------------------------------------------------
    # SAFE SEND
    # --------------------------------------------------

    async def _safe_send(self, websocket: WebSocket, message):
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning("WebSocket send error: %s", e)
            self.disconnect(websocket)

    # --------------------------------------------------
    # STATS
    # --------------------------------------------------

    def stats(self) -> dict:
        with self._lock:
            active = len(self._connections)
            pending = self._pending_accepts
            limit = self._limit()
        return {
            "active": active,
            "connections": active,
            "total": active,
            "limit": limit,
            "pending_accepts": pending,
        }


# =====================================================
# GLOBAL INSTANCE
# =====================================================

manager = ConnectionManager()
