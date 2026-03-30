from fastapi import APIRouter, Depends

from app.cache.signal_cache import get_all_signals
from app.dependencies import require_channel_access

router = APIRouter(dependencies=[Depends(require_channel_access("app"))])


@router.get("/market/radar")
def radar():
    data = []

    for row in get_all_signals():
        if not isinstance(row, dict):
            continue

        if row.get("events"):
            data.append(row)

    data.sort(key=lambda row: float(row.get("score", 0) or 0), reverse=True)
    return data[:20]
