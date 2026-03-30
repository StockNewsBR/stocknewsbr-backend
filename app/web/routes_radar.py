# =====================================================
# STOCKNEWSBR RADAR ROUTES
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

logger = logging.getLogger("stocknewsbr.web.radar")


# =====================================================
# EVENT RADAR
# =====================================================

@router.get("/radar")
def get_radar():

    try:

        signals = signal_cache.get_all()

        if not signals:
            return []

        radar = []

        for s in signals:

            try:

                if s.get("events"):

                    radar.append({

                        "ticker": s.get("ticker"),

                        "events": s.get("events"),

                        "score": s.get("score", 0)

                    })

            except Exception:
                continue

        radar.sort(key=lambda x: x["score"], reverse=True)

        return radar[:20]

    except Exception as e:

        logger.error(f"Radar route error: {e}")

        return []
