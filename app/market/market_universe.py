# =====================================================
# MARKET UNIVERSE (CENTRAL)
# =====================================================

from typing import List

from app.market.b3_core_universe import B3_CORE
from app.market.b3_extended_universe import B3_EXTENDED
from app.market.bdr_universe import BDRS
from app.market.crypto_universe import CRYPTO


# =====================================================
# B3
# =====================================================

def get_b3_universe() -> List[str]:
    return list(B3_CORE + B3_EXTENDED)


# =====================================================
# GLOBAL (BDR)
# =====================================================

def get_global_universe() -> List[str]:
    return list(BDRS)


# =====================================================
# CRYPTO
# =====================================================

def get_crypto_universe() -> List[str]:
    return list(CRYPTO)


# =====================================================
# ALL TICKERS
# =====================================================

def get_all_tickers() -> List[str]:

    universe = (

        B3_CORE
        + B3_EXTENDED
        + BDRS
        + CRYPTO

    )

    seen = set()
    result = []

    for ticker in universe:

        if ticker not in seen:

            seen.add(ticker)
            result.append(ticker)

    return result