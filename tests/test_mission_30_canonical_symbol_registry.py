import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.api import routes_radar
from app.cache.snapshot_cache import SnapshotCache
from app.market import market_data_loader
from app.services import ranking, ticker_room_service
from app.services.public_news_service import _item_belongs_to_symbol, _normalize_public_news_item
from app.services.score_display import normalize_master_score_display
from app.services.snapshot_contract import build_decision_envelope, is_actionable_snapshot_row
from app.services.symbol_sanitizer import sanitize_market_symbol
from app.services.symbol_registry import (
    canonical_symbol,
    canonical_symbol_aliases,
    is_ambiguous_crypto_symbol,
    provider_symbol,
    resolve_tradingview_symbol,
    resolve_tradingview_symbol_candidates,
    symbol_category,
    tradingview_symbol,
)
from app.system import push_dispatcher
from app.telegram.telegram_alert_engine import reset_telegram_alert_state
from app.telegram.telegram_alert_formatter import format_signal_alert
from app.web.routes_search import search_ticker


def actionable_row(ticker: str, score: float = 90.0, **overrides):
    row = {
        "ticker": ticker,
        "symbol": ticker,
        "score": score,
        "master_score": score,
        "master_score_raw": score,
        "score_source_scale": "0_100",
        "master_score_source_scale": "0_100",
        "ranking_opportunity_score": score,
        "ranking_opportunity_source_scale": "0_100",
        "ranking_eligible": True,
        "master_direction": "BULLISH",
        "master_status": "APPROVED",
        "price": 37.5,
        "volume": 1_000_000,
        "trade_action": "BUY",
        "signal": "BUY",
        "data_quality": "priced",
        "decision_ready": True,
        "decision_state": "BUY_READY",
        "audit_status": "APPROVED",
        "operational_status": "READY",
    }
    row.update(overrides)
    return row


class Mission30CanonicalSymbolRegistryTests(unittest.TestCase):
    def setUp(self):
        reset_telegram_alert_state()
        ranking._RANK_CACHE["data"] = []
        ranking._RANK_CACHE["timestamp"] = 0.0
        ranking._RANK_CACHE["snapshot_signature"] = ""

    def test_symbol_registry_resolves_official_aliases(self):
        cases = {
            "PETR": "PETR4",
            "PETR4": "PETR4",
            "PETR4.SA": "PETR4",
            "PETR4 B3": "PETR4",
            "BTCUSD": "BTCUSD",
            "BTCUSDT": "BTCUSD",
            "BTC/USD": "BTCUSD",
            "XBTUSD": "BTCUSD",
            "NASDAQ:AAPL": "AAPL",
            "AAPL.US": "AAPL",
            "WIN$": "WIN",
            "WINFUT": "WIN",
        }
        for raw, expected in cases.items():
            self.assertEqual(canonical_symbol(raw), expected)
        self.assertEqual(canonical_symbol("BTC"), "")
        self.assertTrue(is_ambiguous_crypto_symbol("BTC"))
        results = search_ticker("BTC")
        self.assertNotIn("BTC", results)
        self.assertNotIn("BTCUSD", results)
        qualified_results = search_ticker("BTC.US")
        self.assertNotIn("BTCUSD", qualified_results)

    def test_tradingview_mapping_is_centralized_from_canonical_symbol(self):
        self.assertEqual(tradingview_symbol("PETR4.SA"), "BMFBOVESPA:PETR4")
        self.assertEqual(tradingview_symbol("BTCUSDT"), "BINANCE:BTCUSDT")
        self.assertEqual(tradingview_symbol("NASDAQ:AAPL"), "NASDAQ:AAPL")
        self.assertEqual(tradingview_symbol("WINFUT"), "BMFBOVESPA:WIN1!")

    def test_mission30f_tradingview_uses_real_exchange_for_us_symbols(self):
        cases = {
            "CRM": "NYSE:CRM",
            "NYSE:CRM": "NYSE:CRM",
            "F": "NYSE:F",
            "BULL": "NASDAQ:BULL",
            "BYDDY": "OTC:BYDDY",
            "AAPL": "NASDAQ:AAPL",
            "NVDA": "NASDAQ:NVDA",
            "BNY": "NYSE:BNY",
            "DIA": "NYSEARCA:DIA",
            "IWM": "NYSEARCA:IWM",
            "VOO": "NYSEARCA:VOO",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(resolve_tradingview_symbol(raw), expected)
                self.assertEqual(tradingview_symbol(raw), expected)

    def test_search_normalizes_aliases_to_single_result(self):
        self.assertEqual(search_ticker("PETR")[0], "PETR4")
        self.assertEqual(search_ticker("PETR4.SA")[0], "PETR4")
        self.assertEqual(search_ticker("BTCUSDT")[0], "BTCUSD")

    def test_snapshot_normalizes_and_dedupes_alias_rows(self):
        cache = SnapshotCache()
        cache.update(
            {
                "signals": [
                    actionable_row("PETR4.SA", score=80),
                    actionable_row("PETR4", score=95),
                    actionable_row("BTCUSDT", score=88),
                ],
                "source": "test",
                "stale": False,
            }
        )

        payload = cache.get()
        self.assertEqual([row["ticker"] for row in payload["signals"]], ["PETR4", "BTCUSD"])
        self.assertEqual(set(payload["by_ticker"]), {"PETR4", "BTCUSD"})
        self.assertEqual(cache.get_first_by_ticker(["PETR4.SA"])["ticker"], "PETR4")
        self.assertEqual(cache.get_first_by_ticker(["BTCUSDT"])["ticker"], "BTCUSD")

    def test_ranking_normalizes_and_dedupes_alias_rows(self):
        rows = [
            actionable_row("PETR4.SA", score=86),
            actionable_row("PETR4", score=92),
            actionable_row("VALE3.SA", score=89),
        ]
        with patch.object(ranking, "get_snapshot_info", return_value={"signals": 3, "age_seconds": 5}), patch.object(
            ranking, "get_snapshot_signals", return_value=rows
        ), patch.object(ranking, "fetch_market_data") as fetch_market_data:
            result = ranking.generate_ranking(force_refresh=True)

        fetch_market_data.assert_not_called()
        self.assertEqual([row["symbol"] for row in result], ["PETR4", "VALE3"])

    def test_radar_normalizes_and_dedupes_alias_rows(self):
        rows = [
            actionable_row("PETR4.SA", score=80, radar_prioritization_score=80),
            actionable_row("PETR4", score=91, radar_prioritization_score=91),
            actionable_row("ITUB4.SA", score=87, radar_prioritization_score=87),
        ]
        with patch.object(routes_radar, "get_snapshot_signals", return_value=rows):
            result = routes_radar.radar()

        self.assertEqual([row["symbol"] for row in result], ["PETR4", "ITUB4"])
        self.assertTrue(all(row["canonical_symbol"] == row["symbol"] for row in result))

    def test_telegram_and_push_use_canonical_symbol(self):
        signal = actionable_row("PETR4.SA", score=99)
        self.assertIn("\nPETR4\n", format_signal_alert(signal))
        self.assertNotIn("PETR4.SA", format_signal_alert(signal))

        captured = {}

        class FakeQuery:
            def filter(self, *args, **kwargs):
                return self

            def all(self):
                return [type("User", (), {"id": 1})()]

        class FakeDb:
            def query(self, model):
                return FakeQuery()

            def close(self):
                return None

        def fake_send_push_notification(**kwargs):
            captured.update(kwargs)
            return {"sent": 1}

        with tempfile.TemporaryDirectory() as tempdir, patch.object(
            push_dispatcher, "PUSH_DISPATCH_STATE_PATH", Path(tempdir) / "push_state.json"
        ), patch.object(push_dispatcher, "SessionLocal", return_value=FakeDb()), patch.object(
            push_dispatcher, "get_push_token_store", return_value={"1": ["token"]}
        ), patch.object(push_dispatcher, "send_push_notification", side_effect=fake_send_push_notification):
            result = push_dispatcher.dispatch_signal_pushes([signal])

        self.assertEqual(result["sent"], 1)
        self.assertEqual(captured["data"]["ticker"], "PETR4")
        self.assertEqual(captured["data"]["canonical_symbol"], "PETR4")

    def test_community_room_uses_canonical_symbol(self):
        with tempfile.TemporaryDirectory() as tempdir:
            original = ticker_room_service.ROOM_STORE_PATH
            ticker_room_service.ROOM_STORE_PATH = Path(tempdir) / "rooms.json"
            try:
                message = ticker_room_service.append_room_message("PETR", 10, "Trader", "teste")
                items = ticker_room_service.list_room_messages("PETR4.SA", limit=10)
            finally:
                ticker_room_service.ROOM_STORE_PATH = original

        self.assertEqual(message["symbol"], "PETR4")
        self.assertEqual(items[0]["symbol"], "PETR4")

    def test_news_scope_blocks_cross_ticker_contamination(self):
        self.assertTrue(_item_belongs_to_symbol({"ticker": "PETR4.SA", "title": "Petrobras avanca"}, "PETR"))
        self.assertFalse(_item_belongs_to_symbol({"ticker": "VALE3", "title": "Vale avanca"}, "PETR4"))
        self.assertFalse(_item_belongs_to_symbol({"ticker": "ETHUSDT", "title": "Ethereum sobe"}, "BTCUSD"))
        self.assertFalse(_item_belongs_to_symbol({"ticker": "TSLA", "title": "Tesla entrega carros"}, "AAPL"))

    def test_aliases_include_provider_and_display_forms(self):
        aliases = canonical_symbol_aliases("BTCUSD")
        self.assertIn("BTCUSDT", aliases)
        self.assertIn("BTC-USD", aliases)
        self.assertIn("BTC/USD", aliases)
        self.assertNotIn("BTC", aliases)

    def test_axia_current_codes_replace_legacy_elet_aliases(self):
        self.assertEqual(canonical_symbol("ELET3"), "AXIA3")
        self.assertEqual(canonical_symbol("ELET6"), "AXIA3")
        self.assertEqual(canonical_symbol("AXIA6"), "AXIA3")
        self.assertEqual(provider_symbol("ELET3"), "AXIA3.SA")
        self.assertEqual(provider_symbol("ELET6"), "AXIA3.SA")
        self.assertEqual(provider_symbol("AXIA6"), "AXIA3.SA")
        self.assertEqual(provider_symbol("AXIA7"), "AXIA7.SA")
        self.assertEqual(tradingview_symbol("ELET3"), "BMFBOVESPA:AXIA3")
        self.assertEqual(tradingview_symbol("ELET6"), "BMFBOVESPA:AXIA3")
        self.assertEqual(resolve_tradingview_symbol_candidates("AXIA7")[0], "BMFBOVESPA:AXIA7")
        self.assertNotIn("BMFBOVESPA:AXIA6", resolve_tradingview_symbol_candidates("AXIA7"))
        self.assertIn("BMFBOVESPA:AXIA6", resolve_tradingview_symbol_candidates("AXIA3"))
        self.assertNotIn("AXIA6", canonical_symbol_aliases("AXIA7"))
        self.assertNotIn("ELET6", canonical_symbol_aliases("AXIA7"))
        self.assertEqual(market_data_loader._normalize_symbol("ELET6"), "AXIA3.SA")
        self.assertEqual(market_data_loader._normalize_symbol("AXIA6"), "AXIA3.SA")
        self.assertEqual(market_data_loader.get_display_symbol("AXIA6"), "AXIA3")
        self.assertEqual(market_data_loader.get_display_symbol("ELET6"), "AXIA3")
        self.assertEqual(market_data_loader.get_display_symbol("ELET3"), "AXIA3")
        self.assertEqual(market_data_loader.get_display_symbol("AXIA7.SA"), "AXIA7")

    def test_current_bdr_codes_replace_legacy_aliases(self):
        cases = {
            "AMD34": ("A1MD34", "A1MD34.SA"),
            "AMZN34": ("AMZO34", "AMZO34.SA"),
            "META34": ("M1TA34", "M1TA34.SA"),
        }
        for alias, (canonical, expected_provider) in cases.items():
            with self.subTest(alias=alias):
                self.assertEqual(canonical_symbol(alias), canonical)
                self.assertEqual(provider_symbol(alias), expected_provider)
                self.assertEqual(market_data_loader.get_display_symbol(alias), canonical)
                self.assertEqual(market_data_loader._normalize_symbol(alias), expected_provider)
                self.assertIn(alias, canonical_symbol_aliases(canonical))

    def test_mission30_complement_listed_assets_have_provider_identity(self):
        for symbol in ("ASAI3", "AZUL54", "CPLE6", "B3SA3", "AXIA3", "AXIA7"):
            with self.subTest(symbol=symbol):
                self.assertEqual(canonical_symbol(f"{symbol}.SA"), symbol)
                self.assertEqual(provider_symbol(symbol), f"{symbol}.SA")
                self.assertEqual(tradingview_symbol(symbol), f"BMFBOVESPA:{symbol}")
                self.assertIn(f"BMFBOVESPA:{symbol}", resolve_tradingview_symbol_candidates(symbol))
                self.assertEqual(symbol_category(symbol), "B3")
                self.assertEqual(sanitize_market_symbol(symbol), symbol)

    def test_azul4_is_legacy_alias_of_azul54_and_cple6_is_its_own_canonical(self):
        # B3 renamed AZUL ON from AZUL4 to AZUL54 (Dec/2025): AZUL4 is now legacy.
        self.assertEqual(canonical_symbol("AZUL4"), "AZUL54")
        self.assertEqual(canonical_symbol("AZUL4.SA"), "AZUL54")
        self.assertEqual(provider_symbol("AZUL4"), "AZUL54.SA")
        self.assertEqual(tradingview_symbol("AZUL4"), "BMFBOVESPA:AZUL54")
        self.assertEqual(market_data_loader.get_display_symbol("AZUL4"), "AZUL54")
        self.assertIn("AZUL4", canonical_symbol_aliases("AZUL54"))
        # CPLE6 still trades on its own line — it must not collapse into CPLE3.
        self.assertEqual(canonical_symbol("CPLE6"), "CPLE6")
        self.assertEqual(canonical_symbol("CPLE3"), "CPLE3")
        self.assertEqual(provider_symbol("CPLE6"), "CPLE6.SA")
        self.assertNotIn("CPLE6", canonical_symbol_aliases("CPLE3"))

    def test_mission30_complement_unpriced_asset_is_not_actionable(self):
        row = actionable_row("ASAI3", score=99, price=None, volume=1_000_000, data_quality="missing")
        envelope = build_decision_envelope(row)

        self.assertFalse(is_actionable_snapshot_row(row))
        self.assertFalse(envelope["decision_ready"])
        self.assertIn(envelope["decision_status"], {"INSUFFICIENT_DATA", "NO_TRADE"})
        self.assertEqual(push_dispatcher._eligible_signals([row]), [])

    def test_mission30_complement_news_br_is_portuguese(self):
        item = _normalize_public_news_item(
            {
                "ticker": "PETR4",
                "title": "PETR4 results improve as Petrobras benefits from stronger oil pricing",
                "summary": "Market reads the B3 variant with live supportive pricing.",
                "trader_takeaway": "Trader note: wait for price and volume confirmation.",
                "industry": "Petroleo e gás",
            },
            "PETR4",
            "pt-BR",
        )

        self.assertEqual(item["title"], item["original_title"])
        self.assertIn("results improve", item["title"].lower())
        self.assertEqual(item["content_locale"], "pt-BR")
        self.assertNotIn("market reads", item["summary"].lower())
        self.assertNotIn("live", item["summary"].lower())
        self.assertNotIn("Trader note", item["trader_takeaway"])
        self.assertEqual(item["industry"], "Petróleo e gás")

    def test_mission30_complement_score_warning_scope_keeps_raw_conversion_non_blocking(self):
        from app.services import score_display

        warning_keys = set()
        with patch.object(score_display, "_DISPLAY_WARNING_KEYS", warning_keys):
            with patch.object(score_display.logger, "debug") as debug, patch.object(score_display.logger, "warning") as warning:
                raw_display, raw_warning = normalize_master_score_display(86, source_scale="0_100")
                raw_display_repeat, raw_warning_repeat = normalize_master_score_display(86, source_scale="0_100")
                capped_display, capped_warning = normalize_master_score_display(86, source_scale="0_10")
                capped_display_repeat, capped_warning_repeat = normalize_master_score_display(86, source_scale="0_10")

        self.assertEqual((raw_display, raw_warning), (8.6, "master_score_normalized_from_raw_100"))
        self.assertEqual((raw_display_repeat, raw_warning_repeat), (8.6, "master_score_normalized_from_raw_100"))
        self.assertEqual((capped_display, capped_warning), (10.0, "master_score_display_clamped_above_10"))
        self.assertEqual((capped_display_repeat, capped_warning_repeat), (10.0, "master_score_display_clamped_above_10"))
        self.assertTrue(debug.called)
        self.assertEqual(warning.call_count, 1)
        self.assertIn(("above_10", 86.0, 10.0), warning_keys)
        self.assertNotIn(("raw_100", 86.0, 8.6), warning_keys)


if __name__ == "__main__":
    unittest.main()
