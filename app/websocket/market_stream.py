# =====================================================
# STOCKNEWSBR REALTIME MARKET STREAM
# =====================================================

import asyncio
import logging
from fastapi import WebSocket

logger = logging.getLogger("stocknewsbr.websocket")


connections = set()


# =====================================================
# CONNECT
# =====================================================

async def connect(ws: WebSocket):

    await ws.accept()

    connections.add(ws)


# =====================================================
# DISCONNECT
# =====================================================

def disconnect(ws: WebSocket):

    if ws in connections:

        connections.remove(ws)


# =====================================================
# BROADCAST
# =====================================================

async def broadcast(data):

    dead = []

    for ws in connections:

        try:

            await ws.send_json(data)

        except Exception:

            dead.append(ws)

    for ws in dead:

        disconnect(ws)


# =====================================================
# HEARTBEAT
# =====================================================

async def heartbeat():

    while True:

        await broadcast({"type": "heartbeat"})

        await asyncio.sleep(10)