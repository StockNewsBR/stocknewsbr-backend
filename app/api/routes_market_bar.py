from fastapi import APIRouter, Depends
from app.dependencies import require_channel_access
from app.services.ranking import get_top_movers

router = APIRouter(dependencies=[Depends(require_channel_access("app"))])

@router.get("/market/top_movers")
def top_movers():

    movers = get_top_movers()

    return {
        "tickers": movers
    }
