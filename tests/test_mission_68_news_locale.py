from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from app.api import routes_news, routes_public_market, routes_public_market_live
from app.services import news_service, public_news_service


def _raw_aapl_news() -> list[dict]:
    return [
        {
            "title": "AAPL raises guidance after stronger services revenue",
            "summary": "Apple raised its outlook after services revenue beat expectations.",
            "publisher": "Reuters",
            "link": "https://finance.yahoo.com/news/aapl-guidance",
            "providerPublishTime": 1_743_210_000,
            "relatedTickers": ["AAPL"],
        }
    ]


class Mission68NewsLocaleTests(unittest.TestCase):
    def test_impact_reason_uses_canonical_localized_copy_without_changing_classification(self):
        impact, reason = news_service._impact_from_keywords("raises guidance", ["earnings"], "pt-BR")

        self.assertEqual(impact, "bullish")
        self.assertEqual(reason, "Leitura favorável ao ativo no curto prazo.")
        self.assertEqual(
            news_service._canonical_impact_reason("neutral", "pt-BR", ambiguous_indirect=True),
            "Manchete relevante, mas ainda ambígua ou indireta para o papel; precisa de confirmação.",
        )

    def test_builders_preserve_original_title_and_generate_requested_locale(self):
        original_title = _raw_aapl_news()[0]["title"]

        pt_item = news_service.build_symbol_news("AAPL", _raw_aapl_news(), locale="pt-BR")[0]
        en_item = news_service.build_symbol_news("AAPL", _raw_aapl_news(), locale="en-US")[0]

        self.assertEqual(pt_item["original_title"], original_title)
        self.assertEqual(en_item["original_title"], original_title)
        self.assertEqual(pt_item["content_locale"], "pt-BR")
        self.assertEqual(en_item["content_locale"], "en-US")
        self.assertEqual(pt_item["language"], "en-US")
        self.assertEqual(en_item["language"], "en-US")
        self.assertIn("Para trader:", pt_item["trader_takeaway"])
        self.assertIn("Trader note:", en_item["trader_takeaway"])
        self.assertNotEqual(pt_item["card_summary"], en_item["card_summary"])

    def test_default_locale_remains_pt_br_for_legacy_callers(self):
        item = news_service.build_symbol_news("AAPL", _raw_aapl_news())[0]

        self.assertEqual(item["content_locale"], "pt-BR")
        self.assertEqual(item["original_title"], _raw_aapl_news()[0]["title"])

    def test_cache_only_read_derives_and_isolates_locale_variant(self):
        pt_items = news_service.build_symbol_news("AAPL", _raw_aapl_news(), locale="pt-BR")
        cache_entry = {
            "timestamp": 10_000.0,
            "locale": "pt-BR",
            "items": pt_items,
            "raw_count": 1,
            "status": "ok",
            "report": news_service.build_news_intelligence_report("AAPL", pt_items),
        }
        cache = {"AAPL": {"locales": {"pt-BR": cache_entry}}}

        with patch.object(news_service, "_NEWS_CACHE", cache), patch.object(news_service, "_load_news_cache_once"):
            en_items = news_service.get_cached_symbol_news("AAPL", locale="en-US")
            pt_again = news_service.get_cached_symbol_news("AAPL", locale="pt-BR")
            cache_info = news_service.get_news_cache_info("AAPL", locale="en-US")

            en_items[0]["labels"].append("caller-mutation")
            en_again = news_service.get_cached_symbol_news("AAPL", locale="en-US")

        self.assertEqual(en_items[0]["content_locale"], "en-US")
        self.assertIn("Trader note:", en_items[0]["trader_takeaway"])
        self.assertEqual(pt_again[0]["content_locale"], "pt-BR")
        self.assertIn("Para trader:", pt_again[0]["trader_takeaway"])
        self.assertNotIn("caller-mutation", en_again[0]["labels"])
        self.assertEqual(set(cache["AAPL"]["locales"]), {"pt-BR", "en-US"})
        self.assertEqual(cache_info["locale"], "en-US")
        self.assertEqual(set(cache_info["available_locales"]), {"pt-BR", "en-US"})

    def test_locale_variants_share_provider_fetch_but_not_cached_content(self):
        cache: dict[str, dict] = {}
        with patch.object(news_service, "_NEWS_CACHE", cache), patch.object(
            news_service, "_NEWS_PROVIDER_STATUS", {}
        ), patch.object(news_service, "_REQUEST_LOCKS", {}), patch.object(
            news_service, "_load_news_cache_once"
        ), patch.object(news_service, "_persist_news_cache"), patch.object(
            news_service, "_fetch_yfinance_news", return_value=_raw_aapl_news()
        ) as provider_fetch, patch.object(news_service, "_now_ts", return_value=10_000.0):
            pt_items = news_service.get_symbol_news("AAPL", locale="pt-BR")
            en_items = news_service.get_symbol_news("AAPL", locale="en-US")

        provider_fetch.assert_called_once_with("AAPL")
        self.assertEqual(pt_items[0]["content_locale"], "pt-BR")
        self.assertEqual(en_items[0]["content_locale"], "en-US")
        self.assertIn("Para trader:", pt_items[0]["trader_takeaway"])
        self.assertIn("Trader note:", en_items[0]["trader_takeaway"])
        self.assertEqual(set(cache["AAPL"]["locales"]), {"pt-BR", "en-US"})

    def test_public_contract_is_localized_without_inventing_a_headline(self):
        original_title = "AAPL unveils quantum networking roadmap for data centers"
        cached_item = {
            "id": "aapl-real-1",
            "ticker": "AAPL",
            "title": original_title,
            "summary": "The company published a roadmap for its data-center networking products.",
            "source": "Reuters",
            "url": "https://finance.yahoo.com/news/aapl-networking-roadmap",
            "published_at_source": "2026-07-14T12:00:00+00:00",
            "direct_ticker_match": True,
            "labels": [],
        }
        original_item = copy.deepcopy(cached_item)

        with patch.object(public_news_service, "get_cached_symbol_news", return_value=[cached_item]), patch.object(
            public_news_service, "get_news_cached_report", return_value={"status": "ok"}
        ), patch.object(
            public_news_service,
            "get_news_cache_info",
            return_value={"status": "warm", "provider_status": "ok", "provider": "yfinance"},
        ):
            payload = public_news_service.build_public_news_payload("AAPL", locale="pt-BR")

        item = payload["items"][0]
        self.assertEqual(payload["locale"], "pt-BR")
        self.assertEqual(item["original_title"], original_title)
        self.assertEqual(item["title"], original_title)
        self.assertEqual(item["content_locale"], "pt-BR")
        self.assertEqual(cached_item, original_item)

    def test_partially_translatable_text_stays_in_its_original_language(self):
        # The replacement table only knows a few finance phrases. Swapping the words it does
        # know ("market" -> "mercado") inside an otherwise English sentence used to ship
        # unreadable hybrids like "Why the mercado Dipped But Petrobras Gained Today".
        headline = "Why the market dipped but Petrobras gained today"

        translated = public_news_service._translate_english_news_text(headline, "PETR4", "summary")

        self.assertEqual(translated, headline)
        self.assertNotIn("mercado", translated)

    def test_public_payload_never_emits_a_half_translated_title(self):
        headline = "Why the market dipped but Petrobras gained today"
        cached_item = {
            "id": "petr4-hybrid-1",
            "ticker": "PETR4",
            "title": headline,
            # yfinance frequently omits the summary, and the normalizer falls back to the
            # headline, which is how headline text reached the translator at all.
            "summary": headline,
            "card_summary": headline,
            "source": "Reuters",
            "url": "https://finance.yahoo.com/news/petr4-market-dip",
            "published_at_source": "2026-06-20T12:00:00+00:00",
            "direct_ticker_match": True,
            "labels": [],
        }

        with patch.object(public_news_service, "get_cached_symbol_news", return_value=[cached_item]), patch.object(
            public_news_service, "get_news_cached_report", return_value={"status": "ok"}
        ), patch.object(
            public_news_service,
            "get_news_cache_info",
            return_value={"status": "warm", "provider_status": "ok", "provider": "yfinance"},
        ):
            payload = public_news_service.build_public_news_payload("PETR4", locale="pt-BR")

        item = payload["items"][0]
        for field in ("title", "original_title", "summary", "card_summary"):
            with self.subTest(field=field):
                self.assertEqual(item[field], headline)
                self.assertNotIn("mercado", item[field])
        # The UI still learns the text is not in the requested locale.
        self.assertEqual(item["content_locale"], "pt-BR")
        self.assertEqual(item["language"], "en-US")

    def test_public_payload_orders_items_by_publication_time_descending(self):
        def _item(index: str, published_at: str) -> dict:
            return {
                "id": index,
                "ticker": "PETR4",
                "title": f"Petrobras divulga atualização {index} para PETR4",
                "source": "Reuters",
                "url": f"https://finance.yahoo.com/news/petr4-{index}",
                "published_at_source": published_at,
                "direct_ticker_match": True,
                "labels": [],
            }

        # Provider order is deliberately not chronological.
        cached_items = [
            _item("middle", "2026-06-20T12:00:00+00:00"),
            _item("oldest", "2026-06-18T09:30:00+00:00"),
            _item("newest", "2026-06-21T18:45:00+00:00"),
        ]

        with patch.object(public_news_service, "get_cached_symbol_news", return_value=cached_items), patch.object(
            public_news_service, "get_news_cached_report", return_value={"status": "ok"}
        ), patch.object(
            public_news_service,
            "get_news_cache_info",
            return_value={"status": "warm", "provider_status": "ok", "provider": "yfinance"},
        ):
            payload = public_news_service.build_public_news_payload("PETR4", limit=6)

        published = [item["published_at_source"] for item in payload["items"]]
        self.assertEqual(len(published), 3)
        self.assertEqual(published, sorted(published, reverse=True))
        self.assertEqual([item["id"] for item in payload["items"]], ["newest", "middle", "oldest"])

    def test_public_payload_keeps_source_time_and_exposes_its_local_offset(self):
        cached_item = {
            "id": "petr4-time-1",
            "ticker": "PETR4",
            "title": "Petrobras divulga atualização para PETR4",
            "source": "Reuters",
            "url": "https://finance.yahoo.com/news/petr4-time",
            "published_at_source": "2026-06-20T12:00:00+00:00",
            "fetched_at": "2026-07-19T23:59:00+00:00",
            # Frozen at ingestion; must not survive into the response.
            "age_minutes": 3,
            "is_today": True,
            "direct_ticker_match": True,
            "labels": [],
        }

        with patch.object(public_news_service, "get_cached_symbol_news", return_value=[cached_item]), patch.object(
            public_news_service, "get_news_cached_report", return_value={"status": "ok"}
        ), patch.object(
            public_news_service,
            "get_news_cache_info",
            return_value={"status": "warm", "provider_status": "ok", "provider": "yfinance"},
        ):
            payload = public_news_service.build_public_news_payload("PETR4")

        item = payload["items"][0]
        self.assertEqual(item["published_at"], "2026-06-20T12:00:00+00:00")
        self.assertEqual(item["published_at_source"], "2026-06-20T12:00:00+00:00")
        # Ingestion time never leaks into the published fields.
        self.assertNotEqual(item["published_at"], item["fetched_at"])
        self.assertEqual(item["published_at_local"], "2026-06-20T09:00:00-03:00")
        self.assertEqual(item["published_at_tz"], "America/Sao_Paulo")
        # Recomputed from the article's own time, not read back from the cache.
        self.assertFalse(item["is_today"])
        self.assertTrue(item["is_stale"])
        self.assertGreater(item["age_minutes"], 3)

    def test_stale_cache_is_refreshed_even_when_it_is_full(self):
        cached_items = [
            {
                "id": f"petr4-{index}",
                "ticker": "PETR4",
                "title": f"Petrobras divulga atualização {index} para PETR4",
                "source": "Reuters",
                "url": f"https://finance.yahoo.com/news/petr4-{index}",
                "published_at_source": "2026-06-20T12:00:00+00:00",
                "direct_ticker_match": True,
                "labels": [],
            }
            for index in range(6)
        ]

        for age_seconds, should_refresh in ((10, False), (news_service.NEWS_CACHE_TTL_SECONDS + 1, True)):
            with self.subTest(age_seconds=age_seconds):
                with patch.object(
                    public_news_service, "get_cached_symbol_news", return_value=cached_items
                ), patch.object(
                    public_news_service, "get_symbol_news", return_value=cached_items
                ) as fetch, patch.object(
                    public_news_service, "get_news_cached_report", return_value={"status": "ok"}
                ), patch.object(
                    public_news_service,
                    "get_news_cache_info",
                    return_value={"status": "warm", "provider_status": "ok", "provider": "yfinance", "age_seconds": age_seconds},
                ), patch.object(
                    public_news_service, "_request_news_warmup_safe", return_value=True
                ) as warmup:
                    public_news_service.build_public_news_payload("PETR4", limit=6, allow_fetch=True)
                    public_news_service.build_public_news_payload("PETR4", limit=6, schedule_warmup=True)

                self.assertEqual(fetch.called, should_refresh)
                self.assertEqual(warmup.called, should_refresh)

    def test_news_routes_forward_locale_to_the_shared_contract(self):
        with patch.object(routes_news, "build_public_news_payload", return_value={"locale": "en-US"}) as private_builder:
            routes_news.symbol_news("AAPL", locale="en-US", current_user=object())
        private_builder.assert_called_once_with(
            "AAPL", limit=6, allow_fetch=False, schedule_warmup=True, locale="en-US"
        )

        with patch.object(routes_public_market, "build_public_news_payload", return_value={"locale": "en-US"}) as public_builder:
            routes_public_market.public_news("AAPL", locale="en-US")
        public_builder.assert_called_once_with(
            "AAPL", limit=6, source="public", allow_fetch=False, schedule_warmup=True, locale="en-US"
        )

        with patch.object(routes_public_market_live, "cached_price_payloads", return_value={}), patch.object(
            routes_public_market_live, "_resolve_cached_quote", return_value={"symbol": "AAPL"}
        ), patch.object(routes_public_market_live, "record_cache_access"), patch.object(
            routes_public_market_live, "public_market_insight", return_value={}
        ), patch.object(routes_public_market_live, "public_market_chart", return_value={}), patch.object(
            routes_public_market_live, "build_public_ai_tools_payload", return_value={}
        ), patch.object(
            routes_public_market_live, "build_public_news_payload", return_value={"locale": "en-US"}
        ) as bundle_builder:
            routes_public_market_live.public_market_bundle("AAPL", locale="en-US")
        bundle_builder.assert_called_once_with(
            "AAPL", limit=6, source="public_bundle", allow_fetch=False, schedule_warmup=True, locale="en-US"
        )

    def test_invalid_bundle_normalizes_requested_locale_in_news_contract(self):
        for requested, expected in (("pt", "pt-BR"), ("en", "en-US"), ("invalid", "pt-BR")):
            with self.subTest(requested=requested):
                payload = routes_public_market_live.public_market_bundle("???", locale=requested)
                self.assertEqual(payload["news"]["locale"], expected)


if __name__ == "__main__":
    unittest.main()
