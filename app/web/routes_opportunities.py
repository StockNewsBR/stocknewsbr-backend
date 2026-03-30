# =====================================================
# STOCKNEWSBR OPPORTUNITIES ROUTES
# =====================================================

from fastapi import APIRouter, Depends
import logging

from app.dependencies import require_channel_access
from app.cache.signal_cache import signal_cache
from app.engine.ranking.sorting import sort_signals

router = APIRouter(
    prefix="/web",
    tags=["web"],
    dependencies=[Depends(require_channel_access("web"))],
)

logger = logging.getLogger("stocknewsbr.web.opportunities")


# =====================================================
# TOP OPPORTUNITIES
# =====================================================

@router.get("/opportunities")
def get_opportunities():

    try:

        signals = signal_cache.get_all()

        if not signals:
            return []

        ranked = sort_signals(signals, key="score", limit=25)

        return ranked

    except Exception as e:

        logger.error(f"Opportunities route error: {e}")

        return []
