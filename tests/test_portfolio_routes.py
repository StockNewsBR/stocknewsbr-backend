import unittest
from unittest.mock import patch

from app.api import routes_portfolios


class PortfolioRouteTests(unittest.TestCase):
    def test_portfolio_uses_cached_quotes_only(self):
        with patch.object(
            routes_portfolios,
            "get_portfolio",
            return_value=["PETR4", "VALE3"],
        ), patch.object(
            routes_portfolios,
            "get_cached_quote_payload",
            side_effect=[
                {"price": 38.0, "change": 1.2, "change_pct": 3.3, "source": "snapshot"},
                None,
            ],
        ) as quote_lookup:
            payload = routes_portfolios.portfolio("growth_br")

        self.assertEqual(quote_lookup.call_count, 2)
        self.assertEqual(payload["performance_source"], "cache_snapshot")
        self.assertEqual(payload["performance"]["PETR4"]["change_pct"], 3.3)
        self.assertIsNone(payload["performance"]["VALE3"])


if __name__ == "__main__":
    unittest.main()
