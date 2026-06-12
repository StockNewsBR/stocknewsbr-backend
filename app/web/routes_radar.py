# =====================================================
# STOCKNEWSBR RADAR ROUTES
# =====================================================

from fastapi import APIRouter, Depends
import logging

from app.cache.snapshot_cache import get_snapshot_signals
from app.dependencies import require_channel_access
from app.services.snapshot_contract import is_actionable_snapshot_row, snapshot_surface_row

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

        signals = get_snapshot_signals()

        if not signals:
            return []

        radar = []

        for s in signals:

            try:

                if s.get("events") and is_actionable_snapshot_row(s):

                    item = snapshot_surface_row(s)
                    item["score"] = s.get("master_score", s.get("score", 0))
                    radar.append(item)

            except Exception:
                continue

        radar.sort(key=lambda x: x["score"], reverse=True)

        return radar[:20]

    except Exception as e:

        logger.error(f"Radar route error: {e}")

        return []
