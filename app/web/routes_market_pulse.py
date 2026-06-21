# =====================================================
# STOCKNEWSBR MARKET PULSE ROUTES
# =====================================================

from fastapi import APIRouter, Depends
import logging

from app.ai.ai_market_pulse import market_pulse
from app.cache.snapshot_cache import get_snapshot_signals
from app.dependencies import require_channel_access

router = APIRouter(
    prefix="/web",
    tags=["web"],
    dependencies=[Depends(require_channel_access("web"))],
)

logger = logging.getLogger("stocknewsbr.web.market_pulse")


# =====================================================
# MARKET PULSE
# =====================================================

@router.get("/market-pulse")
def get_market_pulse():

    try:

        return market_pulse(get_snapshot_signals())

    except Exception as e:

        logger.error(f"Market pulse route error: {e}")

        return {}
