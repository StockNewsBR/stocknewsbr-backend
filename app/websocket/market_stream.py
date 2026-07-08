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

    # Mission 31F: itera um snapshot; mutar o set durante o await do send
    # derruba a iteração (RuntimeError: set changed size during iteration).
    for ws in list(connections):

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

        try:

            await broadcast({"type": "heartbeat"})

        except Exception:

            # Mission 31F: heartbeat não pode morrer silenciosamente na
            # primeira exceção; loga e segue para o próximo ciclo.
            logger.warning("Market stream heartbeat error", exc_info=True)

        await asyncio.sleep(10)