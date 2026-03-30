# =====================================================
# STREAM WORKER
# Fast + Crash Safe
# =====================================================

import asyncio
import logging

from app.system.market_stream import broadcast_market


logger = logging.getLogger("stocknewsbr.stream")


# =====================================================
# CONFIG
# =====================================================

STREAM_INTERVAL = 2

_running = False


# =====================================================
# STREAM LOOP
# =====================================================

async def stream_loop():

    global _running

    if _running:
        logger.warning("Stream worker already running")
        return

    _running = True

    logger.info("📡 Market Stream iniciado")

    interval = max(1, int(STREAM_INTERVAL))

    try:

        while _running:

            start = asyncio.get_event_loop().time()

            try:

                await broadcast_market()

            except Exception as e:

                logger.error(f"Stream error: {e}")

            duration = asyncio.get_event_loop().time() - start

            sleep_time = max(0, interval - duration)

            await asyncio.sleep(sleep_time)

    finally:

        _running = False

        logger.info("📡 Market Stream finalizado")


# =====================================================
# STOP WORKER
# =====================================================

def stop_stream():

    global _running

    _running = False