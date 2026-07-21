# =====================================================
# STOCKNEWSBR CONFIG
# =====================================================

import logging
import os

from app.core.settings import DATABASE_URL
from app.services.symbol_sanitizer import sanitize_market_symbol

logger = logging.getLogger("stocknewsbr.config")

# =====================================================
# DATABASE
# =====================================================

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
"WEGE3.SA","EMBJ3.SA","ABEV3.SA","RENT3.SA",
"RAIL3.SA","EQTL3.SA","UGPA3.SA","TOTS3.SA"
]

BDR_SYMBOLS = [
"AAPL34.SA","MSFT34.SA","AMZO34.SA","TSLA34.SA",
"NFLX34.SA","NVDC34.SA","M1TA34.SA"
]

CRYPTO_SYMBOLS = [

"BTCUSDT",
"ETHUSDT",
"SOLUSDT",
"BNBUSDT"

]

_SYMBOL_EXCLUSIONS = {
    "ELET3.SA",
    # CPLE6.SA removed: CPLE6 is a live canonical B3 line (see symbol_registry.py),
    # never present in BR_SYMBOLS, so the entry excluded nothing and only implied
    # the identity was retired.
    "GUAR3.SA",
    "PETZ3.SA",
    "RRRP3.SA",
    "JBSS3.SA",
    "INTC34.SA",
    "AMZN34.SA",
    "MATIC-USD",
}

SYMBOLS = [
    sanitized
    for symbol in BR_SYMBOLS + BDR_SYMBOLS
    if symbol not in _SYMBOL_EXCLUSIONS
    for sanitized in [sanitize_market_symbol(symbol, allow_provider_symbols=True)]
    if sanitized
]

TOTAL_SYMBOLS = len(SYMBOLS)

logger.info(f"Loaded {TOTAL_SYMBOLS} symbols")
