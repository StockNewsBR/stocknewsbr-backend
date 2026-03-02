from fastapi import APIRouter, Depends, HTTPException
import yfinance as yf
from app.dependencies import require_active_plan

router = APIRouter(
    prefix="/market",
    tags=["Market"]
)


@router.get("/quote/{ticker}")
def get_quote(
    ticker: str,
    current_user = Depends(require_active_plan)
):
    stock = yf.Ticker(ticker)
    data = stock.history(period="1d")

    if data.empty:
        raise HTTPException(
            status_code=404,
            detail="Ticker not found"
        )

    return {
        "ticker": ticker.upper(),
        "price": float(data["Close"].iloc[-1]),
        "plan": current_user.plan
    }