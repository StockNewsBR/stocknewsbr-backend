from fastapi import APIRouter, Depends
from app.dependencies import require_channel_access
from app.ai.market_narrative import generate_market_narrative

router = APIRouter(dependencies=[Depends(require_channel_access("app"))])


@router.get("/market/narrative")
def market_narrative():

    return generate_market_narrative()
