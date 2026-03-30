from fastapi import APIRouter, Depends

from app.cache.market_snapshot_cache import get_snapshot, get_snapshot_info
from app.dependencies import require_channel_access

router = APIRouter(dependencies=[Depends(require_channel_access("app"))])


@router.get("/market/snapshot")
def market_snapshot():
    return get_snapshot()


@router.get("/market/snapshot/info")
def snapshot_info():
    return get_snapshot_info()
