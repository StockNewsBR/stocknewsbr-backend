from fastapi import APIRouter

from app.portfolio.model_portfolios import get_portfolio
from app.services.quote_service import get_cached_quote_payload

router = APIRouter()


def _cached_portfolio_performance(tickers):
    performance = {}

    for ticker in tickers or []:
        quote = get_cached_quote_payload(ticker)
        if not quote:
            performance[ticker] = None
            continue

        performance[ticker] = {
            "price": quote.get("price"),
            "change": quote.get("change"),
            "change_pct": quote.get("change_pct"),
            "source": quote.get("source"),
        }

    return performance


@router.get("/portfolio/{name}")
def portfolio(name: str):

    tickers = get_portfolio(name)

    performance = _cached_portfolio_performance(tickers)

    return {

        "portfolio": name,

        "tickers": tickers,

        "performance": performance,
        "performance_source": "cache_snapshot"

    }
