# =====================================================
# STOCKNEWSBR RADAR ROUTES
# =====================================================

from fastapi import APIRouter, Depends
import logging
import math

from app.ai.final_decision import ensure_final_decision_rows
from app.ai.institutional_priority import ensure_institutional_priority_rows
from app.ai.institutional_radar import ensure_institutional_radar_rows, institutional_radar_items
from app.cache.snapshot_cache import get_snapshot_signals
from app.dependencies import require_channel_access
from app.services.score_display import attach_master_score_display_contract
from app.services.snapshot_contract import is_actionable_snapshot_row, snapshot_surface_row

router = APIRouter(
    prefix="/web",
    tags=["web"],
    dependencies=[Depends(require_channel_access("web"))],
)

logger = logging.getLogger("stocknewsbr.web.radar")


def _radar_sort_score(item: dict) -> float:
    display_contract = attach_master_score_display_contract(item if isinstance(item, dict) else {})
    value = display_contract.get("master_score")
    if value is not None and not isinstance(value, bool):
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.0
        if math.isfinite(score) and 0.0 <= score <= 10.0:
            return score
    return 0.0


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

                    item = attach_master_score_display_contract(snapshot_surface_row(s))
                    master_score = item.get("master_score")
                    if master_score is None or isinstance(master_score, bool):
                        numeric_master_score = None
                    else:
                        try:
                            numeric_master_score = float(master_score)
                        except (TypeError, ValueError):
                            numeric_master_score = None
                    item["score"] = (
                        numeric_master_score
                        if numeric_master_score is not None
                        and math.isfinite(numeric_master_score)
                        and 0.0 <= numeric_master_score <= 10.0
                        else None
                    )
                    radar.append(item)

            except Exception:
                continue

        deduped = {}
        for item in radar:
            symbol = item.get("canonical_symbol") or item.get("ticker") or item.get("symbol")
            if not symbol:
                continue
            current = deduped.get(symbol)
            if current is None or _radar_sort_score(item) > _radar_sort_score(current):
                deduped[symbol] = item

        output = list(deduped.values())
        output.sort(key=_radar_sort_score, reverse=True)

        return output[:20]

    except Exception as e:

        logger.error("Radar route error: %s", e)

        return []
