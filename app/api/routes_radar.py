from fastapi import APIRouter, Depends

from app.cache.snapshot_cache import get_snapshot_signals
from app.dependencies import require_channel_access
from app.ai.final_decision import ensure_final_decision_rows
from app.ai.institutional_priority import ensure_institutional_priority_rows
from app.ai.institutional_radar import ensure_institutional_radar_rows, institutional_radar_items
from app.services.snapshot_contract import is_actionable_snapshot_row

router = APIRouter(dependencies=[Depends(require_channel_access("app"))])


@router.get("/market/radar")
def radar():
    data = []

    rows = ensure_final_decision_rows(ensure_institutional_priority_rows(ensure_institutional_radar_rows(get_snapshot_signals())))
    for row in institutional_radar_items(rows, limit=50):
        if not isinstance(row, dict):
            continue

        if is_actionable_snapshot_row(row):
            data.append(row)

    data.sort(key=lambda row: float(row.get("radar_prioritization_score", row.get("master_score", row.get("score", 0))) or 0), reverse=True)
    return data[:20]
