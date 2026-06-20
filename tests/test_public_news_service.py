import unittest
from unittest.mock import patch

from app.services import public_news_service


class PublicNewsServiceTests(unittest.TestCase):
    def test_filters_out_items_from_other_tickers(self):
        fetched_items = [
            {"id": "1", "ticker": "F", "title": "Ford update"},
            {"id": "2", "ticker": "GM", "title": "GM update"},
        ]

        with patch.object(public_news_service, "get_cached_symbol_news", return_value=[]), patch.object(
            public_news_service,
            "get_symbol_news",
            return_value=fetched_items,
        ), patch.object(
            public_news_service,
            "get_news_cached_report",
            return_value={"status": "ok"},
        ), patch.object(
            public_news_service,
            "get_news_cache_info",
            return_value={"status": "warm", "provider_status": "ok", "provider": "yfinance"},
        ):
            payload = public_news_service.build_public_news_payload("F", limit=6, source="public", allow_fetch=True)

        self.assertEqual(payload["symbol"], "F")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["ticker"], "F")
        self.assertEqual(payload["scope"]["filtered_out"], 1)
        self.assertFalse(payload["scope"]["mixed_ticker_allowed"])

    def test_empty_news_state_is_explicit_and_does_not_reuse_other_ticker(self):
        with patch.object(public_news_service, "get_cached_symbol_news", return_value=[]), patch.object(
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
            payload = public_news_service.build_public_news_payload("PETR4", limit=6, allow_fetch=True)

        self.assertEqual(payload["symbol"], "PETR4")
        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["count"], 0)
        self.assertIn("Sem notícia real para PETR4", payload["message"])
        self.assertEqual(payload["scope"]["filtered_out"], 1)

    def test_provider_error_is_exposed(self):
        with patch.object(public_news_service, "get_cached_symbol_news", return_value=[]), patch.object(
            public_news_service,
            "get_symbol_news",
            return_value=[],
        ), patch.object(
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
            payload = public_news_service.build_public_news_payload("AAPL", limit=6, allow_fetch=True)

        self.assertEqual(payload["status"], "provider_error")
        self.assertEqual(payload["state"]["provider_error"], "timeout")
        self.assertIn("timeout", payload["message"])

    def test_cache_only_payload_does_not_fetch_or_request_background_warmup_when_empty(self):
        with patch.object(public_news_service, "get_cached_symbol_news", return_value=[]), patch.object(
            public_news_service,
            "get_symbol_news",
        ) as get_symbol_news, patch.object(
            public_news_service,
            "get_news_cached_report",
            return_value={"status": "empty"},
        ), patch.object(
            public_news_service,
            "get_news_cache_info",
            return_value={"status": "cold", "provider_status": "not_checked", "provider": "yfinance"},
        ):
            payload = public_news_service.build_public_news_payload("F", limit=6, allow_fetch=False)

        self.assertEqual(payload["count"], 0)
        get_symbol_news.assert_not_called()

    def test_cache_only_payload_can_request_background_warmup_when_enabled(self):
        with patch.object(public_news_service, "get_cached_symbol_news", return_value=[]), patch.object(
            public_news_service,
            "get_symbol_news",
        ) as get_symbol_news, patch.object(
            public_news_service,
            "get_news_cached_report",
            return_value={"status": "empty"},
        ), patch.object(
            public_news_service,
            "get_news_cache_info",
            return_value={"status": "cold", "provider_status": "not_checked", "provider": "yfinance"},
        ), patch.object(public_news_service, "_request_news_warmup_safe", return_value=True) as warmup:
            payload = public_news_service.build_public_news_payload("AAPL", limit=6, allow_fetch=False, schedule_warmup=True)

        self.assertEqual(payload["count"], 0)
        self.assertTrue(payload["warmup_requested"])
        self.assertTrue(payload["state"]["warmup_requested"])
        warmup.assert_called_once_with("AAPL", 6)
        get_symbol_news.assert_not_called()

    def test_dedupes_repeated_ticker_news_cards(self):
        fetched_items = [
            {"id": "1", "ticker": "BBDC4", "title": "Resultado e regulacao em BBDC4", "url": "https://example.com/a?utm=1"},
            {"id": "2", "ticker": "BBDC4", "title": "Resultado e regulacao em BBDC4", "url": "https://example.com/a?utm=2"},
            {"id": "3", "ticker": "BBDC4", "title": "Guidance em BBDC4"},
        ]

        with patch.object(public_news_service, "get_cached_symbol_news", return_value=[]), patch.object(
            public_news_service,
            "get_symbol_news",
            return_value=fetched_items,
        ), patch.object(
            public_news_service,
            "get_news_cached_report",
            return_value={"status": "ok"},
        ), patch.object(
            public_news_service,
            "get_news_cache_info",
            return_value={"status": "warm", "provider_status": "ok", "provider": "yfinance"},
        ):
            payload = public_news_service.build_public_news_payload("BBDC4", limit=6, allow_fetch=True)

        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["scope"]["duplicates_removed"], 1)
        self.assertEqual([item["id"] for item in payload["items"]], ["1", "3"])

    def test_single_letter_symbol_matches_company_alias_without_reusing_other_tickers(self):
        fetched_items = [
            {"id": "1", "ticker": "", "title": "Ford Motor confirms new EV plan", "entities": ["Ford Motor"]},
            {"id": "2", "ticker": "", "title": "Finance sector update", "entities": ["Financials"]},
        ]

        with patch.object(public_news_service, "get_cached_symbol_news", return_value=[]), patch.object(
            public_news_service,
            "get_symbol_news",
            return_value=fetched_items,
        ), patch.object(
            public_news_service,
            "get_news_cached_report",
            return_value={"status": "ok"},
        ), patch.object(
            public_news_service,
            "get_news_cache_info",
            return_value={"status": "warm", "provider_status": "ok", "provider": "yfinance"},
        ):
            payload = public_news_service.build_public_news_payload("F", limit=6, allow_fetch=True)

        self.assertEqual(payload["symbol"], "F")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["id"], "1")
        self.assertEqual(payload["scope"]["filtered_out"], 1)

    def test_does_not_accept_artificial_requested_ticker_when_provider_match_is_false(self):
        fetched_items = [
            {
                "id": "1",
                "ticker": "BYDDY",
                "title": "AMD and Intel rise as TSMC capacity tightens",
                "summary": "Semiconductor story without electric vehicle context.",
                "direct_ticker_match": False,
                "entities": ["BYDDY", "AMD", "INTC"],
                "published_at_source": "2026-06-20T12:00:00+00:00",
                "source": "Yahoo Finance",
                "url": "https://finance.yahoo.com/news/amd-intel.html",
            },
            {
                "id": "2",
                "ticker": "BYDDY",
                "title": "BYD expands international delivery network",
                "summary": "BYD Company update with direct ADR context.",
                "direct_ticker_match": False,
                "published_at_source": "2026-06-20T12:10:00+00:00",
                "source": "Yahoo Finance",
                "url": "https://finance.yahoo.com/news/byd-delivery.html",
            },
        ]

        with patch.object(public_news_service, "get_cached_symbol_news", return_value=[]), patch.object(
            public_news_service,
            "get_symbol_news",
            return_value=fetched_items,
        ), patch.object(
            public_news_service,
            "get_news_cached_report",
            return_value={"status": "ok"},
        ), patch.object(
            public_news_service,
            "get_news_cache_info",
            return_value={"status": "warm", "provider_status": "ok", "provider": "yfinance"},
        ):
            payload = public_news_service.build_public_news_payload("BYDDY", limit=6, allow_fetch=True)

        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["id"], "2")
        self.assertEqual(payload["items"][0]["matched_symbol"], "BYDDY")
        self.assertEqual(payload["scope"]["filtered_out"], 1)

    def test_public_payload_exposes_source_time_contract(self):
        fetched_items = [
            {
                "id": "1",
                "ticker": "AAPL",
                "title": "AAPL raises guidance",
                "source": "Reuters",
                "url": "https://example.com/aapl",
                "published_at": "2026-06-20T12:00:00+00:00",
                "direct_ticker_match": True,
                "relevance_score": 92,
            }
        ]

        with patch.object(public_news_service, "get_cached_symbol_news", return_value=[]), patch.object(
            public_news_service,
            "get_symbol_news",
            return_value=fetched_items,
        ), patch.object(
            public_news_service,
            "get_news_cached_report",
            return_value={"status": "ok"},
        ), patch.object(
            public_news_service,
            "get_news_cache_info",
            return_value={"status": "warm", "provider_status": "ok", "provider": "yfinance"},
        ):
            payload = public_news_service.build_public_news_payload("AAPL", limit=6, allow_fetch=True)

        item = payload["items"][0]
        self.assertEqual(item["source_name"], "Reuters")
        self.assertEqual(item["source_url"], "https://example.com/aapl")
        self.assertEqual(item["published_at_source"], "2026-06-20T12:00:00+00:00")
        self.assertIn("age_minutes", item)
        self.assertIn("is_today", item)
        self.assertIn("is_stale", item)
        self.assertEqual(item["matched_symbol"], "AAPL")
        self.assertEqual(item["publication_status"], "ok")
        self.assertFalse(item["is_incomplete"])

    def test_rejects_foreign_company_title_even_when_summary_mentions_requested_symbol(self):
        fetched_items = [
            {
                "id": "1",
                "ticker": "MSFT",
                "title": "Bank of America predicts a major pricing shift for Apple",
                "summary": "The story mentions Microsoft only as one of several AI competitors.",
                "direct_ticker_match": True,
                "published_at_source": "2026-06-20T12:00:00+00:00",
                "source": "TheStreet",
                "url": "https://example.com/apple",
            },
            {
                "id": "2",
                "ticker": "MSFT",
                "title": "Microsoft expands AI infrastructure spending",
                "summary": "Microsoft updates its AI capacity plan.",
                "direct_ticker_match": True,
                "published_at_source": "2026-06-20T12:10:00+00:00",
                "source": "Reuters",
                "url": "https://example.com/msft",
            },
        ]

        with patch.object(public_news_service, "get_cached_symbol_news", return_value=[]), patch.object(
            public_news_service,
            "get_symbol_news",
            return_value=fetched_items,
        ), patch.object(
            public_news_service,
            "get_news_cached_report",
            return_value={"status": "ok"},
        ), patch.object(
            public_news_service,
            "get_news_cache_info",
            return_value={"status": "warm", "provider_status": "ok", "provider": "yfinance"},
        ):
            payload = public_news_service.build_public_news_payload("MSFT", limit=6, allow_fetch=True)

        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["id"], "2")
        self.assertEqual(payload["scope"]["filtered_out"], 1)


if __name__ == "__main__":
    unittest.main()
