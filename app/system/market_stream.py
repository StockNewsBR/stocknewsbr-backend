# =====================================================
# MARKET STREAM
# Fast + Crash Safe
# =====================================================

import logging
from typing import Any

from app.cache.snapshot_cache import get_snapshot
from app.system.websocket_manager import manager


logger = logging.getLogger("stocknewsbr.market_stream")


# =====================================================
# BROADCAST MARKET
# =====================================================

async def broadcast_market():

    try:

        snapshot = get_snapshot()

        if not snapshot:
            return

        # validate snapshot type
        if not isinstance(snapshot, (dict, list)):
            logger.warning("Invalid market snapshot format")
            return

        # shallow copy to avoid mutation
        payload: Any = snapshot.copy() if isinstance(snapshot, dict) else list(snapshot)

        await manager.broadcast(payload)

    except Exception as e:

        logger.error(f"Market broadcast error: {e}")