import unittest
from unittest.mock import patch

from app.api import market_routes
from app.services.public_market_data_service import _payload_matches_symbol
from app.services.score_display import attach_master_score_display_contract, normalize_master_score_display
from app.services.snapshot_runtime_status import SNAPSHOT_RUNTIME_HEALTHY, evaluate_snapshot_runtime_status
from app.services.symbol_registry import resolve_tradingview_symbol, resolve_tradingview_symbol_candidates
from app.social.guardian import SocialGuardian


class Mission31A3CodeRabbitTriageTests(unittest.TestCase):
    def tearDown(self):
        with market_routes.QUOTE_CACHE_LOCK:
            market_routes.QUOTE_CACHE.clear()

    def test_payload_matches_symbol_requires_identity(self):
        self.assertFalse(_payload_matches_symbol({}, "PETR4"))
        self.assertTrue(_payload_matches_symbol({"symbol": "PETR4.SA", "price": 38.8}, "PETR4"))
        self.assertFalse(_payload_matches_symbol({"symbol": "VALE3.SA", "price": 80.0}, "PETR4"))

    def test_social_guardian_rejects_attachment_path_traversal(self):
        self.assertTrue(SocialGuardian.validate_attachment_url("/media/posts/chart.gif").allowed)
        self.assertTrue(SocialGuardian.validate_attachment_url("media/posts/chart.gif").allowed)

        traversal = SocialGuardian.validate_attachment_url("/media/../../../etc/passwd")
        self.assertFalse(traversal.allowed)
        self.assertEqual(traversal.reason, "attachment_path_traversal")

        encoded = SocialGuardian.validate_attachment_url("/media/%2e%2e/%2e%2e/etc/passwd")
        self.assertFalse(encoded.allowed)

    def test_social_guardian_email_regex_allows_mentions_but_blocks_real_email(self):
        self.assertTrue(SocialGuardian.validate_content("@usuario acompanhando PETR4").allowed)
        self.assertTrue(SocialGuardian.validate_content("@R$50 nao e email").allowed)

        decision = SocialGuardian.validate_content("contato fulano@gmail.com")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "email_detected")

    def test_quote_cache_is_locked_and_preserves_hit_miss_contract(self):
        with patch("app.api.market_routes.time.time", return_value=1_000.0):
            market_routes._set_cached_quote("PETR4", {"ticker": "PETR4", "price": 38.8})

        with patch("app.api.market_routes.time.time", return_value=1_010.0):
            self.assertEqual(market_routes._get_cached_quote("PETR4")["price"], 38.8)
            self.assertIsNone(market_routes._get_cached_quote("VALE3"))

        with patch("app.api.market_routes.time.time", return_value=1_031.0):
            self.assertIsNone(market_routes._get_cached_quote("PETR4"))

    def test_market_mover_intensity_preserves_zero_change(self):
        row = {"change": 0.0, "change_pct": 4.2, "momentum": 7.0}
        self.assertEqual(market_routes._market_mover_intensity(row), 0.0)

        fallback_row = {"change": None, "change_pct": -4.2, "momentum": 7.0}
        self.assertEqual(market_routes._market_mover_intensity(fallback_row), 4.2)

    def test_tradingview_invalid_symbol_does_not_fallback_to_petr4(self):
        self.assertEqual(resolve_tradingview_symbol("../PETR4"), "")
        self.assertEqual(resolve_tradingview_symbol_candidates("../PETR4"), tuple())
        self.assertEqual(resolve_tradingview_symbol("PETR4"), "BMFBOVESPA:PETR4")
        self.assertEqual(resolve_tradingview_symbol("AAPL"), "NASDAQ:AAPL")

    def test_snapshot_runtime_preserves_explicit_false_stale(self):
        snapshot = {
            "signals": [{"ticker": "PETR4", "price": 38.8, "volume": 1_000_000}],
            "source": "engine",
            "stale": False,
            "is_stale": True,
            "timestamp": 1_000.0,
        }

        status = evaluate_snapshot_runtime_status(snapshot, now=1_010.0)

        self.assertFalse(status["stale"])
        self.assertEqual(status["status"], SNAPSHOT_RUNTIME_HEALTHY)

    def test_score_display_documents_explicit_raw_100_scale_and_hides_invalid_block_raw(self):
        expected = {
            9.5: 1.0,
            10: 1.0,
            11: 1.1,
            15: 1.5,
            25: 2.5,
            85: 8.5,
        }
        for raw, display in expected.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_master_score_display(raw, source_scale="0_100")[0], display)

        self.assertEqual(normalize_master_score_display(10.5, source_scale="0_10")[0], 10.0)
        self.assertEqual(normalize_master_score_display(10.5, source_scale="0_10")[1], "master_score_display_clamped_above_10")
        self.assertEqual(
            normalize_master_score_display(10.5, source_scale="0_10"),
            (10.0, "master_score_display_clamped_above_10"),
        )

        payload = attach_master_score_display_contract(
            {"master_score_block": {"score_raw": "invalid", "score": "invalid"}}
        )
        self.assertNotIn("score_raw", payload["master_score_block"])
        self.assertEqual(payload["master_score_block"]["score"], 0.0)


if __name__ == "__main__":
    unittest.main()
