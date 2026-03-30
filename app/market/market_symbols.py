# =====================================================
# MARKET SYMBOL UTILITIES
# Fast + Crash Safe
# =====================================================

import logging
from typing import Optional, Dict

logger = logging.getLogger("stocknewsbr.market_symbols")


# =====================================================
# NORMALIZE SYMBOL
# =====================================================

def normalize_symbol(symbol) -> Optional[str]:
    """
    Normaliza símbolo de mercado
    """

    try:

        if not symbol:
            return None

        sym = str(symbol).upper().strip()

        if not sym:
            return None

        return sym

    except Exception as e:

        logger.warning(f"Symbol normalize error: {e}")

        return None


# =====================================================
# MARKET TYPE CHECKS
# =====================================================

def is_brazilian_stock(symbol: str) -> bool:
    """
    Verifica se é ação da B3
    """

    sym = normalize_symbol(symbol)

    if not sym:
        return False

    return sym.endswith(".SA")


def is_crypto(symbol: str) -> bool:
    """
    Verifica se é criptomoeda
    """

    sym = normalize_symbol(symbol)

    if not sym:
        return False

    return sym.endswith("-USD")


def is_us_stock(symbol: str) -> bool:
    """
    Verifica se é ação americana
    """

    sym = normalize_symbol(symbol)

    if not sym:
        return False

    if sym.endswith(".SA"):
        return False

    if sym.endswith("-USD"):
        return False

    return True


# =====================================================
# MARKET TYPE
# =====================================================

def get_market_type(symbol: str) -> Optional[str]:
    """
    Retorna tipo de mercado
    """

    sym = normalize_symbol(symbol)

    if not sym:
        return None

    if sym.endswith("-USD"):
        return "CRYPTO"

    if sym.endswith(".SA"):
        return "B3"

    return "USA"


# =====================================================
# SPLIT SYMBOL + MARKET
# =====================================================

def split_symbol_market(symbol: str) -> Optional[Dict[str, str]]:
    """
    Retorna símbolo e mercado
    """

    sym = normalize_symbol(symbol)

    if not sym:
        return None

    return {

        "symbol": sym,

        "market": get_market_type(sym)

    }