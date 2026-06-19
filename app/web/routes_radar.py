# =====================================================
# STOCKNEWSBR RADAR ROUTES
# =====================================================

from fastapi import APIRouter, Depends
import logging

from app.ai.final_decision import ensure_final_decision_rows
from app.ai.institutional_priority import ensure_institutional_priority_rows
from app.ai.institutional_radar import ensure_institutional_radar_rows, institutional_radar_items
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

        enriched_signals = ensure_final_decision_rows(ensure_institutional_priority_rows(ensure_institutional_radar_rows(signals)))
        for s in institutional_radar_items(enriched_signals, limit=50):

            try:

                if is_actionable_snapshot_row(s):

                    item = snapshot_surface_row(s)
                    item["score"] = s.get("radar_prioritization_score", s.get("master_score", s.get("score", 0)))
                    radar.append(item)

            except Exception:
                continue

        deduped = {}
        for item in radar:
            symbol = item.get("canonical_symbol") or item.get("ticker") or item.get("symbol")
            if not symbol:
                continue
            current = deduped.get(symbol)
            if current is None or float(item.get("score") or 0) > float(current.get("score") or 0):
                deduped[symbol] = item

        output = list(deduped.values())
        output.sort(key=lambda x: x["score"], reverse=True)

        return output[:20]

    except Exception as e:

        logger.error(f"Radar route error: {e}")

        return []
