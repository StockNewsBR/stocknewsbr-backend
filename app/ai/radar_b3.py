# =====================================================
# B3 RADAR
# Fast
# =====================================================

from app.market.market_universe import B3_CORE


def scan_b3():

    try:

        return [

            {
                "ticker": ticker,
                "market": "B3"
            }

            for ticker in B3_CORE

        ]

    except Exception:

        return []