import unittest
from collections import Counter

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_public_meta
from app.market.universe_registry import UniverseRegistry, universe_registry
from app.services.legal_service import get_public_bootstrap


EXPECTED_CATEGORY_COUNTS = {
    "B3": 66,
    "BDR": 11,
    "Crypto": 7,
    "USA": 26,
}


class Mission68CanonicalUniverseTests(unittest.TestCase):
    def test_registry_preserves_every_configured_asset_without_quote_filtering(self):
        assets = universe_registry.get_all_assets()

        self.assertEqual(len(assets), sum(EXPECTED_CATEGORY_COUNTS.values()))
        self.assertEqual(len(assets), len(set(assets)))
        self.assertTrue(
            {"MBRF3", "BRAV3", "EMBJ3", "CPLE3", "JBSS32", "YDUQ3", "AVGO", "DOGEUSD", "AXIA3", "AXIA7"}.issubset(assets)
        )
        self.assertTrue(
            {
                "ELET3", "ELET5", "ELET6", "AXIA5", "AXIA6",
                # Yahoo-dead legacy tickers replaced by successors or delisted
                # (CPLE6 is NOT here — it still trades as its own canonical line):
                "BRFS3", "RRRP3", "MRFG3", "EMBR3", "JBSS3", "CRFB3", "AZUL4",
            }.isdisjoint(assets)
        )

    def test_bootstrap_derives_coherent_categories_union_and_total(self):
        market_universe = get_public_bootstrap()["market_universe"]
        items = market_universe["items"]
        counts = market_universe["counts"]
        identities = {(item["category"], item["symbol"]) for item in items}
        symbols = {item["symbol"] for item in items}

        self.assertEqual(counts, EXPECTED_CATEGORY_COUNTS)
        self.assertEqual(counts, dict(Counter(item["category"] for item in items)))
        self.assertEqual(market_universe["total"], len(items))
        self.assertEqual(market_universe["total"], sum(counts.values()))
        self.assertEqual(len(identities), len(items))
        self.assertEqual(symbols, set(universe_registry.get_all_assets()))

        ivvb11 = next(item for item in items if item["symbol"] == "IVVB11")
        self.assertEqual(ivvb11["category"], "B3")
        self.assertEqual(ivvb11["market"], "B3")

        self.assertTrue({"A1MD34", "AMZO34", "ITLC34", "M1TA34"}.issubset(symbols))
        self.assertTrue({"AMD34", "AMZN34", "INTC34", "META34"}.isdisjoint(symbols))

    def test_public_market_universe_endpoint_matches_bootstrap_contract(self):
        app = FastAPI()
        app.include_router(routes_public_meta.router)
        response = TestClient(app).get("/public/market-universe")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), get_public_bootstrap()["market_universe"])

    def test_public_payload_is_a_defensive_copy(self):
        first = universe_registry.get_public_payload()
        first["items"].clear()
        first["counts"]["B3"] = 0

        second = universe_registry.get_public_payload()
        self.assertEqual(len(second["items"]), second["total"])
        self.assertEqual(second["counts"], EXPECTED_CATEGORY_COUNTS)

    def test_get_all_assets_uses_instance_universes(self):
        registry = UniverseRegistry()
        registry.universes = {"B3": ("TEST3",), "USA": ("TEST", "TEST2")}

        self.assertEqual(registry.get_all_assets(), ["TEST3", "TEST", "TEST2"])


if __name__ == "__main__":
    unittest.main()
