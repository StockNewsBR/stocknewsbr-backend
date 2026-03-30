from fastapi import APIRouter

from app.portfolio.model_portfolios import get_portfolio
from app.portfolio.backtest_engine import backtest_portfolio

router = APIRouter()


@router.get("/portfolio/{name}")
def portfolio(name: str):

    tickers = get_portfolio(name)

    performance = backtest_portfolio(tickers)

    return {

        "portfolio": name,

        "tickers": tickers,

        "performance": performance

    }