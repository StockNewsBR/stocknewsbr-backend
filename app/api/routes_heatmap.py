from fastapi import APIRouter, Depends
from app.dependencies import require_channel_access
from app.ai.market_heatmap import generate_market_heatmap

router = APIRouter(dependencies=[Depends(require_channel_access("app"))])


@router.get("/market/heatmap")
def market_heatmap():

    return generate_market_heatmap()
