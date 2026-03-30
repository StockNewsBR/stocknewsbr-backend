# =====================================================
# STOCKNEWSBR MARKET UNIVERSE ENGINE V3 (INSTITUTIONAL)
# =====================================================

import logging
from typing import List, Dict, Set

logger = logging.getLogger("stocknewsbr.market.universe")


# =====================================================
# DEFAULT UNIVERSES
# =====================================================

B3_UNIVERSE = [
"PETR4","VALE3","ITUB4","BBDC4","BBAS3","ABEV3","SUZB3","WEGE3",
"GGBR4","LREN3","RENT3","RAIL3","JBSS3","PRIO3","VBBR3","EQTL3",
"ELET3","ELET6","CPLE6","UGPA3","TOTS3","MULT3","BRFS3","CSAN3",
"KLBN11","CMIG4","SANB11","RADL3","HYPE3","MRVE3"
]

US_UNIVERSE = [
"AAPL","MSFT","NVDA","AMZN","TSLA","META","GOOGL","AMD",
"INTC","NFLX","PYPL","COIN","UBER","SHOP","CRM","ORCL",
"QCOM","BABA","PDD","ADBE"
]

CRYPTO_UNIVERSE = [
"BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT",
"ADAUSDT","DOGEUSDT","AVAXUSDT","LINKUSDT","MATICUSDT"
]

BDR_UNIVERSE = [
"AAPL34","MSFT34","AMZO34","TSLA34","NVDC34",
"M1TA34","GOGL34","NFLX34","PYPL34"
]

ETF_UNIVERSE = [
"SPY","QQQ","DIA","IWM","VTI","ARKK"
]


# =====================================================
# CONFIG
# =====================================================

ENABLE_B3 = True
ENABLE_US = True
ENABLE_CRYPTO = True
ENABLE_BDR = True
ENABLE_ETF = True


# =====================================================
# INTERNAL REGISTRY
# =====================================================

_UNIVERSE_REGISTRY: Dict[str, List[str]] = {

    "b3": B3_UNIVERSE,
    "us": US_UNIVERSE,
    "crypto": CRYPTO_UNIVERSE,
    "bdr": BDR_UNIVERSE,
    "etf": ETF_UNIVERSE

}

_cached_universe: List[str] = []
_cached_size: int = 0


# =====================================================
# SYMBOL VALIDATION
# =====================================================

def _valid_symbol(symbol: str) -> bool:

    if not symbol:
        return False

    if not isinstance(symbol, str):
        return False

    symbol = symbol.strip()

    if len(symbol) < 2:
        return False

    return True


# =====================================================
# BUILD UNIVERSE
# =====================================================

def _build_universe() -> List[str]:

    try:

        assets: Set[str] = set()

        if ENABLE_B3:
            assets.update(_UNIVERSE_REGISTRY["b3"])

        if ENABLE_US:
            assets.update(_UNIVERSE_REGISTRY["us"])

        if ENABLE_CRYPTO:
            assets.update(_UNIVERSE_REGISTRY["crypto"])

        if ENABLE_BDR:
            assets.update(_UNIVERSE_REGISTRY["bdr"])

        if ENABLE_ETF:
            assets.update(_UNIVERSE_REGISTRY["etf"])

        cleaned: Set[str] = set()

        for symbol in assets:

            if _valid_symbol(symbol):
                cleaned.add(symbol.upper())

        result = list(cleaned)

        result.sort()

        return result

    except Exception as e:

        logger.exception("Universe build error: %s", e)

        return []


# =====================================================
# GET FULL UNIVERSE
# =====================================================

def get_full_universe(force_refresh: bool = False) -> List[str]:

    global _cached_universe
    global _cached_size

    try:

        if _cached_universe and not force_refresh:
            return _cached_universe

        universe = _build_universe()

        _cached_universe = universe
        _cached_size = len(universe)

        logger.info("Universe built | assets=%s", _cached_size)

        return universe

    except Exception as e:

        logger.exception("Universe retrieval error: %s", e)

        return []


# =====================================================
# UNIVERSE SIZE
# =====================================================

def get_universe_size() -> int:

    try:

        if _cached_universe:
            return _cached_size

        return len(get_full_universe())

    except Exception:

        return 0


# =====================================================
# REGISTER NEW UNIVERSE
# =====================================================

def register_universe(name: str, universe: List[str]):

    try:

        if not name or not universe:
            return

        _UNIVERSE_REGISTRY[name] = universe

        global _cached_universe
        _cached_universe = []

        logger.info("Universe registered | %s | size=%s", name, len(universe))

    except Exception:

        logger.exception("Universe registration failed")


# =====================================================
# ENABLE / DISABLE MARKET
# =====================================================

def enable_market(name: str, enabled: bool):

    global ENABLE_B3
    global ENABLE_US
    global ENABLE_CRYPTO
    global ENABLE_BDR
    global ENABLE_ETF

    try:

        if name == "b3":
            ENABLE_B3 = enabled

        elif name == "us":
            ENABLE_US = enabled

        elif name == "crypto":
            ENABLE_CRYPTO = enabled

        elif name == "bdr":
            ENABLE_BDR = enabled

        elif name == "etf":
            ENABLE_ETF = enabled

        global _cached_universe
        _cached_universe = []

    except Exception:

        logger.exception("Market toggle failed")