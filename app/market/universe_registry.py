# =====================================================
# MARKET UNIVERSE REGISTRY
# =====================================================

import logging

from app.market.b3_core_universe import B3_CORE
from app.market.b3_extended_universe import B3_EXTENDED
from app.market.bdr_universe import BDRS
from app.market.crypto_universe import CRYPTO

logger = logging.getLogger("stocknewsbr.market.universe_registry")


class UniverseRegistry:
    """
    Central registry of all market universes.

    Combines multiple universes into one list of tickers
    used by the market loader and engine.
    """

    def __init__(self):

        self.universes = {
            "b3_core": B3_CORE,
            "b3_extended": B3_EXTENDED,
            "bdr": BDRS,
            "crypto": CRYPTO,
        }

    def get_universe(self, name):

        return self.universes.get(name, [])

    def get_all_assets(self):

        assets = []

        for universe_name, universe in self.universes.items():

            try:

                assets.extend(universe)

            except Exception:

                logger.warning(f"Universe failed: {universe_name}")

        # remove duplicates
        assets = list(set(assets))

        assets.sort()

        logger.info(f"Universe built | assets={len(assets)}")

        return assets


# global instance
universe_registry = UniverseRegistry()
