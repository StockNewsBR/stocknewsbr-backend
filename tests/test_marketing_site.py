import unittest

from app.Frontend.marketing_site import get_marketing_site
from app.web import routes_site


class MarketingSiteTests(unittest.TestCase):
    def test_marketing_site_contains_core_conversion_copy(self):
        html = get_marketing_site()

        self.assertIn("Transforme complexidade institucional em decisao simples", html)
        self.assertIn("Score Mestre", html)
        self.assertIn("Auditor Institucional", html)
        self.assertIn("Ranking", html)
        self.assertIn("Radar", html)
        self.assertIn("30 dias", html)
        self.assertIn("15 dias", html)
        self.assertIn("FAQ", html)
        self.assertIn("Testar Gratuitamente", html)

    def test_public_site_route_returns_marketing_page(self):
        html = routes_site.public_site()

        self.assertIn("StockNewsBR", html)
        self.assertIn("Plano", html)
        self.assertIn("Entrar no Telegram", html)


if __name__ == "__main__":
    unittest.main()
