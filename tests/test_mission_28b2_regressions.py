import unittest
from pathlib import Path
from unittest.mock import patch

from app.engine.market_snapshot_engine import _canonicalize_master_score_surfaces
from app.services import news_service
from app.services.public_news_service import build_public_news_payload
from app.telegram.telegram_alert_formatter import format_signal_alert


REPO_ROOT = Path(__file__).resolve().parents[1]


def _raw_ford_news():
    return [
        {
            "id": "ford-1",
            "content": {
                "title": "Ford shares rise after EV battery update",
                "summary": "Ford Motor said its electric vehicle battery plan is improving margins.",
                "provider": {"displayName": "Reuters"},
                "canonicalUrl": {"url": "https://example.com/ford-ev-battery-update"},
                "pubDate": "2026-06-15T12:30:00Z",
                "finance": {"stockTickers": [{"symbol": "F"}]},
            },
        }
    ]


class Mission28B2RegressionTests(unittest.TestCase):
    def setUp(self):
        news_service._NEWS_CACHE.clear()
        news_service._NEWS_PROVIDER_STATUS.clear()
        news_service._NEWS_CACHE_LOADED = True

    def test_ford_raw_news_populates_symbol_cache_and_public_payload(self):
        news_service._remember_news_provider_status("F", "ok", raw_count=10)

        with patch.object(news_service, "_fetch_yfinance_news", return_value=_raw_ford_news()), \
             patch.object(news_service, "_persist_news_cache_locked"):
            items = news_service.get_symbol_news("F", limit=6)

        self.assertGreater(len(items), 0)
        self.assertIn("F", news_service._NEWS_CACHE)
        self.assertGreater(len(news_service._NEWS_CACHE["F"]["items"]), 0)

        payload = build_public_news_payload("F", limit=6, allow_fetch=False)

        self.assertEqual(payload["status"], "ok")
        self.assertGreater(payload["count"], 0)
        item = payload["items"][0]
        self.assertEqual(item["ticker"], "F")
        self.assertTrue(item["title"])
        self.assertTrue(item["source"])
        self.assertTrue(item["published_at"])

    def test_public_news_empty_state_includes_reason_when_provider_had_raw_items(self):
        news_service._remember_news_provider_status("F", "ok", raw_count=10)

        payload = build_public_news_payload("F", limit=6, allow_fetch=False)

        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["reason"], "cache_missing_after_provider_raw")
        self.assertEqual(payload["cache"]["raw_count"], 10)
        self.assertIn("cache_missing_after_provider_raw", payload["message"])

    def test_score_surfaces_expose_canonical_master_score_and_preserve_raw(self):
        payload = {
            "signals": [{"ticker": "F", "master_score": 87.0, "score": 42.0}],
            "leaders": [{"ticker": "F", "master_score": 87.0}],
            "master_scores": [{"ticker": "F", "tool": "master_score", "master_score": 87.0, "score": 87.0}],
            "master_score": {"ticker": "F", "tool": "master_score", "master_score": 87.0, "score": 87.0},
            "institutional_radar": [{"ticker": "F", "master_score": 87.0}],
            "institutional_ranking": [{"ticker": "F", "master_score": 87.0}],
            "symbol_snapshots": {"F": {"ticker": "F", "master_score": 87.0}},
        }

        normalized = _canonicalize_master_score_surfaces(payload)

        self.assertEqual(normalized["signals"][0]["master_score"], 8.7)
        self.assertEqual(normalized["signals"][0]["master_score_raw"], 87.0)
        self.assertEqual(normalized["signals"][0]["score"], 42.0)
        self.assertEqual(normalized["master_score"]["master_score"], 8.7)
        self.assertEqual(normalized["master_score"]["score"], 8.7)
        self.assertEqual(normalized["institutional_ranking"][0]["master_score"], 8.7)
        self.assertEqual(normalized["symbol_snapshots"]["F"]["master_score"], 8.7)

    def test_telegram_alert_uses_canonical_master_score(self):
        message = format_signal_alert(
            {
                "ticker": "F",
                "final_decision": "OPORTUNIDADE CONFIRMADA",
                "master_score": 87.0,
                "audit_status": "APPROVED",
                "conviction_level": "ALTA",
                "priority_level": "ALTA",
                "historical_confidence_score": 72,
                "telegram_summary": "Fluxo confirmado.",
            }
        )

        self.assertIn("Score Mestre: 8.7", message)
        self.assertNotIn("Score Mestre: 87", message)

    def test_frontend_contract_keeps_rsi_panel_from_remounting_chart_levels(self):
        ticker_chart = (REPO_ROOT / "apps/web/components/ticker-chart.tsx").read_text(encoding="utf-8")
        css = (REPO_ROOT / "apps/web/app/globals.css").read_text(encoding="utf-8")

        self.assertNotIn("RSI@tv-basicstudies", ticker_chart)
        self.assertIn('aria-hidden={!showRsi}', ticker_chart)
        self.assertIn('className={`snbr-institutional-rsi-panel ${rsiPanelTone} ${showRsi ? "" : "hidden"}`}', ticker_chart)
        self.assertIn(".snbr-institutional-rsi-panel.hidden", css)
        self.assertIn("supportLevel", ticker_chart)
        self.assertIn("resistanceLevel", ticker_chart)

    def test_frontend_ai_empty_states_and_basic_header_are_explicit(self):
        shell = (REPO_ROOT / "apps/web/components/workspace-shell.tsx").read_text(encoding="utf-8")
        sections = (REPO_ROOT / "apps/web/components/workspace-sections.tsx").read_text(encoding="utf-8")
        rails = (REPO_ROOT / "apps/web/components/workspace-rails.tsx").read_text(encoding="utf-8")

        self.assertIn("Nenhum achado desta IA para este ativo agora.", shell)
        self.assertIn("IA temporariamente sem dados.", shell)
        self.assertIn('<div className="snbr-price-line">', shell)
        self.assertIn("🔒 Disponível no Pro", shell)
        self.assertIn('"Alta"', sections)
        self.assertIn('"Baixa"', sections)
        self.assertIn("Inteligência de Mercado com IA", rails)


if __name__ == "__main__":
    unittest.main()
