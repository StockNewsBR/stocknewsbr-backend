# =====================================================
# STOCKNEWSBR MARKET PULSE ROUTES
# =====================================================

from fastapi import APIRouter, Depends
import logging

from app.dependencies import require_channel_access
from app.cache.signal_cache import signal_cache

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

        signals = signal_cache.get_all()

        if not signals:
            return {}

        bullish = 0
        bearish = 0

        for s in signals:

            try:

                score = s.get("score", 0)

                if score >= 70:
                    bullish += 1

                elif score <= 30:
                    bearish += 1

            except Exception:
                continue

        total = len(signals)

        if total == 0:
            return {}

        return {

            "bullish": bullish,
            "bearish": bearish,
            "neutral": total - bullish - bearish,
            "total_signals": total

        }

    except Exception as e:

        logger.error(f"Market pulse route error: {e}")

        return {}
