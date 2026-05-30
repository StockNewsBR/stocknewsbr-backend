import unittest
from unittest.mock import patch

from app.services import public_news_service


class PublicNewsServiceTests(unittest.TestCase):
    def test_filters_out_items_from_other_tickers(self):
        fetched_items = [
            {"id": "1", "ticker": "F", "title": "Ford update"},
            {"id": "2", "ticker": "GM", "title": "GM update"},
        ]

        with patch.object(public_news_service, "get_symbol_news", return_value=fetched_items), patch.object(
            public_news_service,
            "get_news_cached_report",
            return_value={"status": "ok"},
        ), patch.object(
            public_news_service,
            "get_news_cache_info",
            return_value={"status": "warm", "provider_status": "ok", "provider": "yfinance"},
        ):
            payload = public_news_service.build_public_news_payload("F", limit=6, source="public")

        self.assertEqual(payload["symbol"], "F")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["ticker"], "F")
        self.assertEqual(payload["scope"]["filtered_out"], 1)
        self.assertFalse(payload["scope"]["mixed_ticker_allowed"])

    def test_empty_news_state_is_explicit_and_does_not_reuse_other_ticker(self):
        with patch.object(
            public_news_service,
            "get_symbol_news",
            return_value=[{"id": "1", "ticker": "AAPL", "title": "Apple update"}],
        ), patch.object(
            public_news_service,
            "get_news_cached_report",
            return_value={"status": "empty"},
        ), patch.object(
            public_news_service,
            "get_news_cache_info",
            return_value={"status": "empty", "provider_status": "empty_response", "provider": "yfinance"},
        ):
            payload = public_news_service.build_public_news_payload("PETR4", limit=6)

        self.assertEqual(payload["symbol"], "PETR4")
        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["count"], 0)
        self.assertIn("Sem noticia real para PETR4", payload["message"])
        self.assertEqual(payload["scope"]["filtered_out"], 1)

    def test_provider_error_is_exposed(self):
        with patch.object(public_news_service, "get_symbol_news", return_value=[]), patch.object(
            public_news_service,
            "get_news_cached_report",
            return_value={"status": "empty"},
        ), patch.object(
            public_news_service,
            "get_news_cache_info",
            return_value={
                "status": "cold",
                "provider_status": "provider_error",
                "provider_error": "timeout",
                "provider": "yfinance",
            },
        ):
            payload = public_news_service.build_public_news_payload("AAPL", limit=6)

        self.assertEqual(payload["status"], "provider_error")
        self.assertEqual(payload["state"]["provider_error"], "timeout")
        self.assertIn("timeout", payload["message"])

    def test_dedupes_repeated_ticker_news_cards(self):
        fetched_items = [
            {"id": "1", "ticker": "BBDC4", "title": "Resultado e regulacao em BBDC4", "url": "https://example.com/a?utm=1"},
            {"id": "2", "ticker": "BBDC4", "title": "Resultado e regulacao em BBDC4", "url": "https://example.com/a?utm=2"},
            {"id": "3", "ticker": "BBDC4", "title": "Guidance em BBDC4"},
        ]

        with patch.object(public_news_service, "get_symbol_news", return_value=fetched_items), patch.object(
            public_news_service,
            "get_news_cached_report",
            return_value={"status": "ok"},
        ), patch.object(
            public_news_service,
            "get_news_cache_info",
            return_value={"status": "warm", "provider_status": "ok", "provider": "yfinance"},
        ):
            payload = public_news_service.build_public_news_payload("BBDC4", limit=6)

        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["scope"]["duplicates_removed"], 1)
        self.assertEqual([item["id"] for item in payload["items"]], ["1", "3"])

    def test_single_letter_symbol_matches_company_alias_without_reusing_other_tickers(self):
        fetched_items = [
            {"id": "1", "ticker": "", "title": "Ford Motor confirms new EV plan", "entities": ["Ford Motor"]},
            {"id": "2", "ticker": "", "title": "Finance sector update", "entities": ["Financials"]},
        ]

        with patch.object(public_news_service, "get_symbol_news", return_value=fetched_items), patch.object(
            public_news_service,
            "get_news_cached_report",
            return_value={"status": "ok"},
        ), patch.object(
            public_news_service,
            "get_news_cache_info",
            return_value={"status": "warm", "provider_status": "ok", "provider": "yfinance"},
        ):
            payload = public_news_service.build_public_news_payload("F", limit=6)

        self.assertEqual(payload["symbol"], "F")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["id"], "1")
        self.assertEqual(payload["scope"]["filtered_out"], 1)


if __name__ == "__main__":
    unittest.main()
