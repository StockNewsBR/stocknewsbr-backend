from fastapi import APIRouter, Depends

from app.cache.snapshot_cache import get_snapshot_signals
from app.dependencies import require_channel_access
from app.services.snapshot_contract import is_actionable_snapshot_row

router = APIRouter(dependencies=[Depends(require_channel_access("app"))])


@router.get("/market/radar")
def radar():
    data = []

    for row in get_snapshot_signals():
        if not isinstance(row, dict):
            continue

        if row.get("events") and is_actionable_snapshot_row(row):
            data.append(row)

    data.sort(key=lambda row: float(row.get("master_score", row.get("score", 0)) or 0), reverse=True)
    return data[:20]
