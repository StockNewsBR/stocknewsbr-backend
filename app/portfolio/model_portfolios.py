# =====================================================
# STOCKNEWSBR MODEL PORTFOLIOS
# =====================================================

import logging
from typing import List, Dict
from functools import lru_cache

logger = logging.getLogger("stocknewsbr.portfolio")

# =====================================================
# PORTFOLIO DEFINITIONS
# =====================================================

PORTFOLIOS: Dict[str, List[str]] = {

    "growth_br": [

        "WEGE3",
        "PRIO3",
        "LREN3",
        "TOTS3"

    ],

    "dividends": [

        "TAEE11",
        "BBAS3",
        "ITSA4",
        "EGIE3"

    ],

    "momentum_us": [

        "NVDA",
        "TSLA",
        "META",
        "AMZN"

    ]

}


# =====================================================
# GET PORTFOLIO
# =====================================================

@lru_cache(maxsize=128)
def _get_portfolio_cached(name: str):
    portfolio = PORTFOLIOS.get(name)
    if not portfolio:
        return ()
    return tuple(portfolio)

def get_portfolio(name: str) -> List[str]:

    portfolio_tuple = _get_portfolio_cached(name)

    if not portfolio_tuple:

        logger.warning(f"Portfolio not found: {name}")

        return []

    # return copy to prevent mutation
    return list(portfolio_tuple)


# =====================================================
# LIST PORTFOLIOS
# =====================================================

def list_portfolios() -> List[str]:

    return list(PORTFOLIOS.keys())


# =====================================================
# CHECK PORTFOLIO
# =====================================================

def portfolio_exists(name: str) -> bool:

    return name in PORTFOLIOS