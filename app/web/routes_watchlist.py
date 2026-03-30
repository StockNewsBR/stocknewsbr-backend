# =====================================================
# STOCKNEWSBR WATCHLIST ROUTES
# =====================================================

from fastapi import APIRouter, Depends
import logging

from app.dependencies import require_channel_access
from app.watchlists.watchlist_default import (
    WATCHLIST_B3,
    WATCHLIST_US_GLOBAL,
    WATCHLIST_BDR,
    WATCHLIST_CRYPTO
)

router = APIRouter(
    prefix="/web",
    tags=["web"],
    dependencies=[Depends(require_channel_access("web"))],
)

logger = logging.getLogger("stocknewsbr.web.watchlist")


# =====================================================
# ALL WATCHLISTS
# =====================================================

@router.get("/watchlists")
def get_watchlists():

    try:

        return {

            "b3": WATCHLIST_B3,

            "us": WATCHLIST_US_GLOBAL,

            "bdr": WATCHLIST_BDR,

            "crypto": WATCHLIST_CRYPTO

        }

    except Exception as e:

        logger.error(f"Watchlist route error: {e}")

        return {}


# =====================================================
# SINGLE WATCHLIST
# =====================================================

@router.get("/watchlists/{market}")
def get_watchlist(market: str):

    try:

        market = market.lower()

        if market == "b3":
            return {"tickers": WATCHLIST_B3}

        if market == "us":
            return {"tickers": WATCHLIST_US_GLOBAL}

        if market == "bdr":
            return {"tickers": WATCHLIST_BDR}

        if market == "crypto":
            return {"tickers": WATCHLIST_CRYPTO}

        return {"tickers": []}

    except Exception as e:

        logger.error(f"Watchlist market error: {e}")

        return {"tickers": []}
