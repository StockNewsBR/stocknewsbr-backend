# =====================================================
# ENGINE SHARDS
# =====================================================

from app.market.market_universe import (
    B3_CORE,
    B3_EXTENDED,
    BDRS,
    USA_STOCKS,
    CRYPTO
)


def build_shards():

    return [
        B3_CORE,
        B3_EXTENDED,
        BDRS,
        USA_STOCKS,
        CRYPTO
    ]