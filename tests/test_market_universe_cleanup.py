import unittest

from app.config import SYMBOLS
from app.market.market_universe import get_b3_universe, get_all_tickers
from app.market.universe_engine_v3 import get_full_universe


class MarketUniverseCleanupTests(unittest.TestCase):
    def test_b3_universe_excludes_known_noisy_ticker(self):
        universe = get_b3_universe()
        self.assertNotIn("ELET3.SA", universe)

    def test_full_universe_excludes_legacy_matic_symbol(self):
        universe = get_full_universe(force_refresh=True)
        self.assertNotIn("MATICUSDT", universe)
        self.assertNotIn("MATIC-USD", universe)
        self.assertGreater(len(get_all_tickers()), 0)

    def test_config_symbols_exclude_bad_amazon_bdr_variants(self):
        self.assertNotIn("AMZN34.SA", SYMBOLS)
        self.assertIn("AMZO34.SA", SYMBOLS)
        self.assertIn("M1TA34.SA", SYMBOLS)

    def test_config_bdr_universe_uses_correct_amazon_symbol(self):
        from app.config import BDR_SYMBOLS

        self.assertIn("AMZO34.SA", BDR_SYMBOLS)
        self.assertIn("M1TA34.SA", BDR_SYMBOLS)
        self.assertNotIn("AMZN34.SA", BDR_SYMBOLS)
        self.assertNotIn("META34.SA", BDR_SYMBOLS)


if __name__ == "__main__":
    unittest.main()
