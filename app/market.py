from fastapi import APIRouter
import yfinance as yf

router = APIRouter(prefix="/market", tags=["Market"])


@router.get("/quote/{ticker}")
def get_quote(ticker: str):
    stock = yf.Ticker(ticker)
    data = stock.history(period="1d")

    if data.empty:
        return {"error": "Ticker not found"}

    return {
        "ticker": ticker.upper(),
        "price": float(data["Close"].iloc[-1])
    }