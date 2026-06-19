import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import news_service
from app.services.news_service import (
    build_news_intelligence_report,
    build_news_quality_report,
    build_symbol_news,
    compare_news_runs,
    get_cached_symbol_news,
    get_news_cache_info,
    get_news_cached_report,
    get_symbol_news,
)


class NewsServiceTests(unittest.TestCase):
    def setUp(self):
        news_service._NEWS_CACHE.clear()
        news_service._NEWS_PROVIDER_STATUS.clear()
        news_service._NEWS_CACHE_LOADED = True
        try:
            news_service._NEWS_CACHE_FILE_MTIME = news_service._NEWS_CACHE_FILE.stat().st_mtime
        except FileNotFoundError:
            news_service._NEWS_CACHE_FILE_MTIME = None

    def test_build_symbol_news_dedupes_and_labels_useful_items(self):
        raw_items = [
            {
                "title": "PETR4 reports strong quarterly results and raises guidance",
                "summary": "Quarterly earnings beat estimates and the company raised full-year guidance.",
                "publisher": "Reuters",
                "link": "https://example.com/a",
                "providerPublishTime": 1_743_000_000,
                "relatedTickers": ["PETR4"],
            },
            {
                "title": "Petrobras reports strong quarterly results and raises guidance",
                "summary": "Quarterly earnings beat estimates and the company raised full-year guidance.",
                "publisher": "Yahoo Finance",
                "link": "https://example.com/b",
                "providerPublishTime": 1_743_000_060,
                "relatedTickers": ["PETR4"],
            },
            {
                "title": "Fed leaves rates unchanged and signals higher for longer",
                "summary": "Macro backdrop remains tight and pressuring risk assets.",
                "publisher": "AP",
                "link": "https://example.com/c",
                "providerPublishTime": 1_743_000_120,
            },
        ]

        items = build_symbol_news("PETR4", raw_items, limit=6)

        self.assertEqual(len(items), 2)
        result_item = items[0]
        macro_item = items[1]

        self.assertIn("resultado", result_item["labels"])
        self.assertIn("guidance", result_item["labels"])
        self.assertGreaterEqual(result_item["same_story_count"], 2)
        self.assertTrue(items[0]["useful"])
        self.assertTrue(result_item["card_summary"])
        self.assertTrue(result_item["why_it_matters"])
        self.assertTrue(result_item["editorial"])
        self.assertIn("macro", macro_item["labels"])
        self.assertIn(macro_item["impact"], {"bearish", "neutral"})

    def test_build_symbol_news_marks_macro_items_and_rankings(self):
        raw_items = [
            {
                "title": "Fed hints higher rates for longer as inflation cools slowly",
                "summary": "Macro news can move the whole market and the sector beta.",
                "publisher": "Bloomberg",
                "link": "https://example.com/macro",
                "providerPublishTime": 1_743_100_000,
            },
            {
                "title": "Company files 8-K about a new contract",
                "summary": "The announcement is a factual update and should be read together with the price trend.",
                "publisher": "SEC",
                "link": "https://example.com/fato",
                "providerPublishTime": 1_743_099_000,
            },
        ]

        items = build_symbol_news("AAPL", raw_items, limit=6)

        self.assertEqual(len(items), 2)
        macro_item = next(item for item in items if "macro" in item["labels"])
        fact_item = next(item for item in items if "fato relevante" in item["labels"])
        self.assertGreaterEqual(macro_item["ranking_score"], fact_item["ranking_score"] - 20)
        self.assertIn(macro_item["impact"], {"bullish", "bearish", "neutral"})
        self.assertIn(fact_item["impact"], {"bullish", "bearish", "neutral"})

    def test_build_symbol_news_marks_ambiguous_indirect_macro_story(self):
        raw_items = [
            {
                "title": "Could tariffs hit exporters if macro fears grow?",
                "summary": "Analysts debate whether pressure may spread across exporters and risk assets, without citar a empresa diretamente.",
                "publisher": "Reuters",
                "link": "https://example.com/ambiguous",
                "providerPublishTime": 1_743_200_000,
            }
        ]

        items = build_symbol_news("PETR4", raw_items, limit=6)

        self.assertEqual(len(items), 1)
        self.assertGreaterEqual(items[0]["ambiguity_score"], 45)
        self.assertFalse(items[0]["direct_ticker_match"])
        self.assertIn("impacto_indireto", items[0]["ambiguity_flags"])
        self.assertTrue(items[0]["trader_takeaway"])

    def test_build_symbol_news_adds_detection_time_when_provider_time_missing(self):
        raw_items = [
            {
                "title": "Ford Motor confirms new EV plan",
                "summary": "Ford updates its electric vehicle strategy.",
                "publisher": "Yahoo Finance",
                "link": "https://example.com/ford",
                "relatedTickers": ["F"],
            }
        ]

        items = build_symbol_news("F", raw_items, limit=6)

        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0]["published_at"])
        self.assertFalse(items[0]["source_published_at"])
        self.assertRegex(items[0]["detected_at"], r"^\d{4}-\d{2}-\d{2}T")

    def test_build_symbol_news_keeps_source_publication_time_separate_from_detection_time(self):
        raw_items = [
            {
                "title": "AAPL raises guidance after strong iPhone demand",
                "summary": "The company improved the outlook after stronger demand.",
                "publisher": "Reuters",
                "link": "https://example.com/aapl-source-time",
                "providerPublishTime": 1_743_210_000,
                "relatedTickers": ["AAPL"],
            },
        ]

        with patch("app.services.news_service._now_ts", return_value=1_743_300_000):
            items = build_symbol_news("AAPL", raw_items, limit=6)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["published_at"], "2025-03-29T01:00:00+00:00")
        self.assertEqual(items[0]["detected_at"], "2025-03-30T02:00:00+00:00")
        self.assertTrue(items[0]["source_published_at"])

    def test_build_symbol_news_counts_multiple_sources_per_story(self):
        raw_items = [
            {
                "title": "AAPL raises guidance after strong iPhone demand",
                "summary": "The company improved the outlook after stronger demand.",
                "publisher": "Reuters",
                "link": "https://example.com/aapl-a",
                "providerPublishTime": 1_743_210_000,
                "relatedTickers": ["AAPL"],
            },
            {
                "title": "Apple raises guidance after strong iPhone demand",
                "summary": "Outlook improved after better-than-expected iPhone demand.",
                "publisher": "Bloomberg",
                "link": "https://example.com/aapl-b",
                "providerPublishTime": 1_743_210_030,
                "relatedTickers": ["AAPL"],
            },
        ]

        items = build_symbol_news("AAPL", raw_items, limit=6)

        self.assertEqual(len(items), 1)
        self.assertGreaterEqual(items[0]["same_story_count"], 2)
        self.assertGreaterEqual(items[0]["source_count"], 2)
        self.assertIn("Reuters", items[0]["sources"])
        self.assertIn("Bloomberg", items[0]["sources"])

    def test_quality_report_and_compare_runs_work(self):
        previous = build_symbol_news(
            "PETR4",
            [
                {
                    "title": "PETR4 reports quarterly results in line with estimates",
                    "summary": "The market reads the earnings release with neutral tone.",
                    "publisher": "Reuters",
                    "link": "https://example.com/prev",
                    "providerPublishTime": 1_743_220_000,
                    "relatedTickers": ["PETR4"],
                }
            ],
            limit=6,
        )
        current = build_symbol_news(
            "PETR4",
            [
                {
                    "title": "PETR4 reports strong quarterly results and raises guidance",
                    "summary": "Quarterly earnings beat estimates and the company raised full-year guidance.",
                    "publisher": "Reuters",
                    "link": "https://example.com/current-a",
                    "providerPublishTime": 1_743_230_000,
                    "relatedTickers": ["PETR4"],
                },
                {
                    "title": "Petrobras raises guidance after strong quarter",
                    "summary": "Guidance improved after a stronger-than-expected quarter.",
                    "publisher": "Bloomberg",
                    "link": "https://example.com/current-b",
                    "providerPublishTime": 1_743_230_030,
                    "relatedTickers": ["PETR4"],
                },
            ],
            limit=6,
        )

        report = build_news_quality_report("PETR4", current)
        comparison = compare_news_runs(previous, current)

        self.assertEqual(report["ticker"], "PETR4")
        self.assertGreaterEqual(report["count"], 1)
        self.assertGreaterEqual(report["useful_count"], 1)
        self.assertTrue(report["top_labels"])
        self.assertIn("added_story_keys", comparison)
        self.assertIn("removed_story_keys", comparison)
        self.assertIn("ranking_moves", comparison)

    def test_news_intelligence_report_summarizes_context_and_alerts(self):
        items = build_symbol_news(
            "PETR4",
            [
                {
                    "title": "PETR4 reports strong quarterly results and raises guidance",
                    "summary": "Quarterly earnings beat estimates and the company raised full-year guidance.",
                    "publisher": "Reuters",
                    "link": "https://example.com/current-a",
                    "providerPublishTime": 1_743_230_000,
                    "relatedTickers": ["PETR4"],
                },
                {
                    "title": "Petrobras raises guidance after strong quarter",
                    "summary": "Guidance improved after a stronger-than-expected quarter.",
                    "publisher": "Bloomberg",
                    "link": "https://example.com/current-b",
                    "providerPublishTime": 1_743_230_030,
                    "relatedTickers": ["PETR4"],
                },
            ],
            limit=6,
        )

        report = build_news_intelligence_report("PETR4", items)

        self.assertEqual(report["ticker"], "PETR4")
        self.assertEqual(report["status"], "ok")
        self.assertTrue(report["dominant_labels"])
        self.assertTrue(report["top_story_title"])
        self.assertTrue(report["editorial_summary"])
        self.assertTrue(report["trader_takeaway"])
        self.assertGreaterEqual(report["unique_story_count"], 1)
        self.assertGreaterEqual(report["source_count"], 1)

    def test_get_symbol_news_marks_stale_fallback_in_cache(self):
        fresh_items = build_symbol_news(
            "PETR4",
            [
                {
                    "title": "PETR4 reports strong quarterly results and raises guidance",
                    "summary": "Quarterly earnings beat estimates and the company raised full-year guidance.",
                    "publisher": "Reuters",
                    "link": "https://example.com/a",
                    "providerPublishTime": 1_743_000_000,
                    "relatedTickers": ["PETR4"],
                }
            ],
            limit=6,
        )

        with patch("app.services.news_service._NEWS_CACHE", {"PETR4": {"timestamp": 0.0, "items": fresh_items, "raw_count": 1, "status": "ok", "fallback_used": False, "fetched_from": "yfinance", "report": build_news_intelligence_report("PETR4", fresh_items)}}), patch(
            "app.services.news_service._fetch_yfinance_news",
            return_value=[],
        ), patch(
            "app.services.news_service._now_ts",
            return_value=10_000.0,
        ):
            items = get_symbol_news("PETR4", limit=6)
            cache = get_news_cache_info("PETR4")

        self.assertEqual(items[0]["ticker"], "PETR4")
        self.assertEqual(cache["status"], "stale_fallback")
        self.assertTrue(cache["fallback_used"])
        self.assertEqual(cache["fetched_from"], "stale_cache")

    def test_get_symbol_news_exposes_provider_error_when_yahoo_unavailable(self):
        with patch("app.services.news_service._NEWS_CACHE", {}), patch(
            "app.services.news_service._NEWS_PROVIDER_STATUS",
            {},
        ), patch(
            "app.services.news_service._get_yfinance",
            return_value=None,
        ), patch(
            "app.services.news_service._now_ts",
            return_value=10_000.0,
        ):
            items = get_symbol_news("ZZZZ", limit=3)
            cache = get_news_cache_info("ZZZZ")

        self.assertEqual(items, [])
        self.assertEqual(cache["status"], "empty")
        self.assertEqual(cache["provider"], "yfinance")
        self.assertEqual(cache["provider_status"], "dependency_unavailable")
        self.assertEqual(cache["provider_error"], "dependency_unavailable")
        self.assertEqual(cache["attempted_candidates"], ["ZZZZ"])

    def test_get_symbol_news_tries_b3_symbol_variants(self):
        with patch(
            "app.services.news_service._fetch_yfinance_news",
            side_effect=lambda ticker: [
                {
                    "title": "PETR4 results improve as Petrobras benefits from stronger oil pricing",
                    "summary": "Market reads the B3 variant as live.",
                    "publisher": "Reuters",
                    "link": "https://example.com/petr4",
                    "providerPublishTime": 1_743_300_000,
                    "relatedTickers": ["PETR4"],
                }
            ] if ticker == "PETR4.SA" else [],
        ):
            items = get_symbol_news("PETR4", limit=3)

        self.assertTrue(items)
        self.assertEqual(items[0]["ticker"], "PETR4")
        self.assertIn("resultado", items[0]["labels"])

    def test_get_news_cached_report_reuses_cached_payload(self):
        items = build_symbol_news(
            "PETR4",
            [
                {
                    "title": "PETR4 reports strong quarterly results and raises guidance",
                    "summary": "Quarterly earnings beat estimates and the company raised full-year guidance.",
                    "publisher": "Reuters",
                    "link": "https://example.com/a",
                    "providerPublishTime": 1_743_000_000,
                    "relatedTickers": ["PETR4"],
                }
            ],
            limit=6,
        )
        cached_report = build_news_intelligence_report("PETR4", items)

        with patch("app.services.news_service._NEWS_CACHE", {"PETR4": {"timestamp": 1.0, "items": items, "report": cached_report}}):
            report = get_news_cached_report("PETR4", [])

        self.assertEqual(report["ticker"], "PETR4")
        self.assertEqual(report["top_story_title"], cached_report["top_story_title"])

    def test_cached_news_reloads_when_shared_cache_file_changes(self):
        first_item = {
            "id": "aapl-1",
            "story_key": "aapl-1",
            "title": "AAPL supplier update supports Apple demand",
            "summary": "Apple demand remains relevant for the stock.",
            "ticker": "AAPL",
            "relatedTickers": ["AAPL"],
        }
        second_item = {
            **first_item,
            "id": "aapl-2",
            "story_key": "aapl-2",
            "title": "AAPL services revenue keeps Apple in focus",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "news_cache.json"
            with patch("app.services.news_service._NEWS_CACHE_FILE", cache_file):
                news_service._NEWS_CACHE.clear()
                news_service._NEWS_PROVIDER_STATUS.clear()
                news_service._NEWS_CACHE_LOADED = False
                news_service._NEWS_CACHE_FILE_MTIME = None

                self.assertEqual(get_cached_symbol_news("AAPL", limit=6), [])

                cache_file.write_text(
                    json.dumps(
                        {
                            "news_cache": {"AAPL": {"timestamp": 1.0, "items": [first_item], "raw_count": 1, "status": "ok"}},
                            "provider_status": {"AAPL": {"provider": "yfinance", "ticker": "AAPL", "status": "ok", "raw_count": 1}},
                        }
                    ),
                    encoding="utf-8",
                )
                loaded = get_cached_symbol_news("AAPL", limit=6)
                self.assertEqual(loaded[0]["title"], first_item["title"])

                cache_file.write_text(
                    json.dumps(
                        {
                            "news_cache": {"AAPL": {"timestamp": 2.0, "items": [second_item], "raw_count": 1, "status": "ok"}},
                            "provider_status": {"AAPL": {"provider": "yfinance", "ticker": "AAPL", "status": "ok", "raw_count": 1}},
                        }
                    ),
                    encoding="utf-8",
                )
                next_mtime = cache_file.stat().st_mtime + 10
                os.utime(cache_file, (next_mtime, next_mtime))

                reloaded = get_cached_symbol_news("AAPL", limit=6)
                self.assertEqual(reloaded[0]["title"], second_item["title"])

    def test_persist_news_cache_merges_shared_file_before_write(self):
        aapl_item = {
            "id": "aapl-1",
            "story_key": "aapl-1",
            "title": "AAPL services revenue keeps Apple in focus",
            "summary": "Apple remains relevant for the market.",
            "ticker": "AAPL",
            "relatedTickers": ["AAPL"],
        }
        nvda_item = {
            "id": "nvda-1",
            "story_key": "nvda-1",
            "title": "NVDA demand update keeps Nvidia in focus",
            "summary": "Nvidia remains relevant for the market.",
            "ticker": "NVDA",
            "relatedTickers": ["NVDA"],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "news_cache.json"
            cache_file.write_text(
                json.dumps(
                    {
                        "news_cache": {"NVDA": {"timestamp": 2.0, "items": [nvda_item], "raw_count": 1, "status": "ok"}},
                        "provider_status": {"NVDA": {"provider": "yfinance", "ticker": "NVDA", "status": "ok", "raw_count": 1, "checked_at": 2.0}},
                    }
                ),
                encoding="utf-8",
            )
            disk_mtime = cache_file.stat().st_mtime

            with patch("app.services.news_service._NEWS_CACHE_FILE", cache_file):
                news_service._NEWS_CACHE.clear()
                news_service._NEWS_PROVIDER_STATUS.clear()
                news_service._NEWS_CACHE["AAPL"] = {"timestamp": 3.0, "items": [aapl_item], "raw_count": 1, "status": "ok"}
                news_service._NEWS_PROVIDER_STATUS["AAPL"] = {"provider": "yfinance", "ticker": "AAPL", "status": "ok", "raw_count": 1, "checked_at": 3.0}
                news_service._NEWS_CACHE_LOADED = True
                news_service._NEWS_CACHE_FILE_MTIME = disk_mtime - 10

                news_service._persist_news_cache_locked()

                payload = json.loads(cache_file.read_text(encoding="utf-8"))
                self.assertIn("AAPL", payload["news_cache"])
                self.assertIn("NVDA", payload["news_cache"])


if __name__ == "__main__":
    unittest.main()
