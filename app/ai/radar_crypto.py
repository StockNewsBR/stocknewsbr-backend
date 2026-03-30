# =====================================================
# CRYPTO RADAR
# Fast
# =====================================================

from app.market.market_universe import CRYPTO


def scan_crypto_market():

    try:

        return [

            {
                "ticker": ticker,
                "market": "CRYPTO"
            }

            for ticker in CRYPTO

        ]

    except Exception:

        return []