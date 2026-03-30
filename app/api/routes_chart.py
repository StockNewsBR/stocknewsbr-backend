from fastapi import APIRouter
from app.market.market_data_loader import get_chart_data

router = APIRouter()

@router.get("/chart/{symbol}")
def chart(symbol: str, interval: str = "1D"):

    data = get_chart_data(symbol, interval)

    return {
        "symbol": symbol,
        "interval": interval,
        "data": data
    }