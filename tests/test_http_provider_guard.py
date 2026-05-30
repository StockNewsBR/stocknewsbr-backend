from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTTP_ROUTE_DIRS = (ROOT / "app" / "api", ROOT / "app" / "web")
FORBIDDEN_HTTP_PATTERNS = (
    "get_chart_data(",
    "get_price_snapshot(",
    "get_price_snapshots(",
    "get_market_data(",
    "get_symbol_news(",
    "market_data_cache.get",
    "backtest_engine",
    "backtest_portfolio(",
    "ai_market_radar",
    "async_market_loader",
    "yf.download",
    "yf.Ticker",
    "import yfinance",
    "allow_fetch=True",
)


class HttpProviderGuardTests(unittest.TestCase):
    def test_api_and_web_routes_do_not_call_market_providers(self):
        violations = []

        for route_dir in HTTP_ROUTE_DIRS:
            for path in route_dir.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                for pattern in FORBIDDEN_HTTP_PATTERNS:
                    if pattern in text:
                        violations.append(f"{path.relative_to(ROOT)} contains {pattern}")

        self.assertEqual(violations, [])

    def test_public_market_service_is_cache_only_for_http_surfaces(self):
        service_path = ROOT / "app" / "services" / "public_market_data_service.py"
        text = service_path.read_text(encoding="utf-8")

        self.assertNotIn("get_chart_data", text)
        self.assertNotIn("get_price_snapshots", text)
        self.assertNotIn("refreshed_price_payloads", text)


if __name__ == "__main__":
    unittest.main()
