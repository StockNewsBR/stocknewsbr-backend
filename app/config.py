# =====================================================
# STOCKNEWSBR CONFIG
# =====================================================

import os
import logging

logger = logging.getLogger("stocknewsbr.config")

# =====================================================
# DATABASE
# =====================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./stocknews.db"
)

# =====================================================
# ENGINE
# =====================================================

UPDATE_INTERVAL = int(
    os.getenv("UPDATE_INTERVAL", 60)
)

# =====================================================
# SIGNAL CONFIG
# =====================================================

MIN_SCORE_ALERT = int(
    os.getenv("MIN_SCORE_ALERT", 80)
)

TOP_RANKING_LIMIT = int(
    os.getenv("TOP_RANKING_LIMIT", 10)
)

# =====================================================
# STOCK UNIVERSE
# =====================================================

BR_SYMBOLS = [
"PETR3.SA","PETR4.SA","VALE3.SA","ITUB4.SA",
"BBDC3.SA","BBDC4.SA","BBAS3.SA","B3SA3.SA",
"MGLU3.SA","LREN3.SA","PRIO3.SA","CSNA3.SA",
"GGBR4.SA","USIM5.SA","SUZB3.SA","KLBN11.SA",
"WEGE3.SA","EMBR3.SA"
]

BDR_SYMBOLS = [
"AAPL34.SA","MSFT34.SA","AMZO34.SA","TSLA34.SA",
"NFLX34.SA","NVDC34.SA","PYPL34.SA"
]

CRYPTO_SYMBOLS = [

"BTCUSDT",
"ETHUSDT",
"SOLUSDT",
"BNBUSDT"

]

SYMBOLS = BR_SYMBOLS + BDR_SYMBOLS

TOTAL_SYMBOLS = len(SYMBOLS)

logger.info(f"Loaded {TOTAL_SYMBOLS} symbols")