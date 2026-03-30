# =====================================================
# STOCKNEWSBR MODEL PORTFOLIOS
# =====================================================

import logging
from typing import List, Dict

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

def get_portfolio(name: str) -> List[str]:

    portfolio = PORTFOLIOS.get(name)

    if not portfolio:

        logger.warning(f"Portfolio not found: {name}")

        return []

    # return copy to prevent mutation
    return list(portfolio)


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