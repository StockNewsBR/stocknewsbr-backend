import shutil
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

try:
    from app.services import poll_service
    IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    IMPORT_ERROR = exc


@unittest.skipIf(IMPORT_ERROR is not None, f"runtime dependency unavailable: {IMPORT_ERROR}")
class PollServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_path = poll_service.POLL_STORE_PATH
        poll_service.POLL_STORE_PATH = Path(self.temp_dir) / "weekly_polls.json"

    def tearDown(self):
        poll_service.POLL_STORE_PATH = self.original_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_creates_stock_poll(self):
        signal = {
            "ticker": "PETR4",
            "score": 82,
            "trend": 2.8,
            "change_pct": 3.2,
            "rsi": 63,
            "adx": 31,
            "rel_volume": 1.7,
            "sector": "Energy",
            "signal": "breakout",
        }

        poll = poll_service.ensure_weekly_poll("PETR4", signal=signal)

        self.assertEqual(poll["symbol"], "PETR4")
        self.assertEqual(len(poll["options"]), 2)
        self.assertTrue(poll["question"])
        self.assertEqual(poll["market_type"], "stock")
        self.assertEqual(poll["timing_bucket"], "trend_following")
        self.assertTrue(poll["report"]["why_it_matters"])
        self.assertGreaterEqual(len(poll["question_variants"]), 2)
        self.assertEqual(poll["context"]["signal"]["ticker"], "PETR4")

    def test_detects_earnings_week(self):
        signal = {
            "ticker": "VALE3",
            "score": 76,
            "signal": "resultado e guidance fortes",
            "events": ["earnings release", "guidance"],
        }

        with patch.object(poll_service, "_week_key", return_value="2026-W17"):
            poll = poll_service.ensure_weekly_poll("VALE3", signal=signal)

        self.assertTrue(poll["earnings_week"])
        self.assertEqual(poll["timing_bucket"], "earnings_week")
        self.assertIn("result", poll["question"].lower())
        self.assertNotIn("vai bater o anúncio", poll["question"].lower())
        self.assertEqual(poll["report"]["market_type"], "stock")

    def test_detects_structured_earnings_date_inside_current_week(self):
        signal = {
            "ticker": "VALE3",
            "score": 72,
            "earnings_date": "2026-05-14",
            "sector": "Materials",
        }
        now = datetime(2026, 5, 13, 14, 0, tzinfo=UTC)

        with patch.object(poll_service, "_utc_now", return_value=now), patch.object(
            poll_service,
            "_week_key",
            return_value="2026-W20",
        ):
            poll = poll_service.ensure_weekly_poll("VALE3", signal=signal)

        self.assertTrue(poll["earnings_week"])
        self.assertEqual(poll["timing_bucket"], "earnings_week")
        self.assertEqual(poll["context"]["earnings_date"], "2026-05-14")
        self.assertEqual(poll["context"]["earnings_source"], "earnings_date")
        self.assertIn("resultado", poll["question"].lower())
        self.assertNotIn("vai bater", poll["question"].lower())

    def test_structured_earnings_date_outside_current_week_is_not_earnings_poll(self):
        signal = {
            "ticker": "VALE3",
            "score": 72,
            "earnings_date": "2026-06-03",
        }
        now = datetime(2026, 5, 13, 14, 0, tzinfo=UTC)

        with patch.object(poll_service, "_utc_now", return_value=now), patch.object(
            poll_service,
            "_week_key",
            return_value="2026-W20",
        ):
            poll = poll_service.ensure_weekly_poll("VALE3", signal=signal)

        self.assertFalse(poll["earnings_week"])
        self.assertNotEqual(poll["timing_bucket"], "earnings_week")
        self.assertEqual(poll["context"]["earnings_date"], "2026-06-03")
        self.assertIn("fora da semana", poll["context"]["earnings_reason"])

    def test_generates_crypto_specific_poll(self):
        signal = {
            "ticker": "BTCUSDT",
            "score": 88,
            "trend": 5.1,
            "change_pct": 6.4,
            "rsi": 77,
            "adx": 34,
            "rel_volume": 2.3,
            "signal": "momentum",
        }

        poll = poll_service.ensure_weekly_poll("BTCUSDT", market_type="crypto", signal=signal)

        self.assertEqual(poll["market_type"], "crypto")
        self.assertIn(poll["timing_bucket"], {"crypto_momentum", "crypto_overheated"})
        self.assertTrue(poll["question"])
        self.assertEqual(poll["report"]["market_type"], "crypto")

    def test_existing_poll_reclassifies_when_richer_signal_arrives(self):
        with patch.object(poll_service, "_week_key", return_value="2026-W17"):
            initial = poll_service.ensure_weekly_poll("VALE3")
            enriched = poll_service.ensure_weekly_poll(
                "VALE3",
                signal={
                    "ticker": "VALE3",
                    "score": 79,
                    "signal": "resultado forte com guidance",
                    "events": ["earnings release"],
                    "sector": "Materials",
                },
            )

        self.assertEqual(initial["timing_bucket"], "weekly_direction")
        self.assertTrue(enriched["earnings_week"])
        self.assertEqual(enriched["timing_bucket"], "earnings_week")
        self.assertNotEqual(initial["question"], enriched["question"])
        self.assertEqual(enriched["context"]["sector"], "Materials")

    def test_vote_replaces_previous_vote(self):
        poll_service.ensure_weekly_poll("BTCUSDT", market_type="crypto")
        poll = poll_service.vote_poll("BTCUSDT", "A", user_id=10)
        poll = poll_service.vote_poll("BTCUSDT", "B", user_id=10)

        option_a = next(item for item in poll["options"] if item["key"] == "A")
        option_b = next(item for item in poll["options"] if item["key"] == "B")

        self.assertEqual(option_a["votes"], 0)
        self.assertEqual(option_b["votes"], 1)

    def test_generate_weekly_polls_for_top_symbols_is_bounded(self):
        snapshot = {
            "BTCUSDT": {"ticker": "BTCUSDT", "symbol": "BTCUSDT", "score": 99, "signal": "crypto"},
            "PETR4": {"ticker": "PETR4", "symbol": "PETR4", "score": 85, "sector": "Energy"},
            "VALE3": {"ticker": "VALE3", "symbol": "VALE3", "score": 83, "sector": "Materials"},
            "ITUB4": {"ticker": "ITUB4", "symbol": "ITUB4", "score": 80, "sector": "Financials"},
        }

        with patch.object(poll_service, "_week_key", return_value="2026-W17"), patch.object(
            poll_service,
            "get_snapshot_by_ticker",
            return_value=snapshot,
        ):
            created = poll_service.generate_weekly_polls_for_top_symbols(limit=1)

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["symbol"], "BTCUSDT")

    def test_generate_weekly_polls_includes_diverse_context(self):
        snapshot = {
            "PETR4": {"ticker": "PETR4", "symbol": "PETR4", "score": 95, "sector": "Energy", "signal": "trend"},
            "VALE3": {"ticker": "VALE3", "symbol": "VALE3", "score": 90, "sector": "Materials", "signal": "trend"},
            "ITUB4": {"ticker": "ITUB4", "symbol": "ITUB4", "score": 85, "sector": "Financials", "signal": "trend"},
            "BTCUSDT": {"ticker": "BTCUSDT", "symbol": "BTCUSDT", "score": 88, "signal": "crypto"},
        }

        with patch.object(poll_service, "_week_key", return_value="2026-W17"), patch.object(
            poll_service,
            "get_snapshot_by_ticker",
            return_value=snapshot,
        ):
            created = poll_service.generate_weekly_polls_for_top_symbols(limit=4)

        symbols = {item["symbol"] for item in created}
        self.assertEqual(len(created), 4)
        self.assertIn("BTCUSDT", symbols)
        self.assertGreaterEqual(len({item["timing_bucket"] for item in created}), 2)

    def test_generate_weekly_polls_prioritizes_earnings_week_candidate(self):
        now = datetime(2026, 5, 13, 14, 0, tzinfo=UTC)
        snapshot = {
            "AAPL": {"ticker": "AAPL", "symbol": "AAPL", "score": 96, "sector": "Technology", "signal": "trend"},
            "MSFT": {"ticker": "MSFT", "symbol": "MSFT", "score": 95, "sector": "Technology", "signal": "trend"},
            "VALE3": {"ticker": "VALE3", "symbol": "VALE3", "score": 44, "sector": "Materials", "earnings_date": "2026-05-14"},
            "BTCUSDT": {"ticker": "BTCUSDT", "symbol": "BTCUSDT", "score": 99, "signal": "crypto"},
        }

        with patch.object(poll_service, "_utc_now", return_value=now), patch.object(
            poll_service,
            "_week_key",
            return_value="2026-W20",
        ), patch.object(
            poll_service,
            "get_snapshot_by_ticker",
            return_value=snapshot,
        ):
            created = poll_service.generate_weekly_polls_for_top_symbols(limit=3)

        by_symbol = {item["symbol"]: item for item in created}
        self.assertIn("VALE3", by_symbol)
        self.assertTrue(by_symbol["VALE3"]["earnings_week"])
        self.assertEqual(by_symbol["VALE3"]["timing_bucket"], "earnings_week")

    def test_generate_weekly_polls_rebalances_when_one_side_is_short(self):
        snapshot = {
            "AAA3": {"ticker": "AAA3", "symbol": "AAA3", "score": 99, "sector": "Energy"},
            "BBB3": {"ticker": "BBB3", "symbol": "BBB3", "score": 98, "sector": "Energy"},
            "CCC3": {"ticker": "CCC3", "symbol": "CCC3", "score": 97, "sector": "Energy"},
            "DDD3": {"ticker": "DDD3", "symbol": "DDD3", "score": 96, "sector": "Energy"},
            "EEE3": {"ticker": "EEE3", "symbol": "EEE3", "score": 95, "sector": "Energy"},
            "BTCUSDT": {"ticker": "BTCUSDT", "symbol": "BTCUSDT", "score": 94},
            "ETHUSDT": {"ticker": "ETHUSDT", "symbol": "ETHUSDT", "score": 93},
        }

        with patch.object(poll_service, "_week_key", return_value="2026-W17"), patch.object(
            poll_service,
            "get_snapshot_by_ticker",
            return_value=snapshot,
        ):
            created = poll_service.generate_weekly_polls_for_top_symbols(limit=6)

        self.assertEqual(len(created), 6)

    def test_poll_report_does_not_persist_when_poll_is_missing(self):
        with patch.object(
            poll_service,
            "get_snapshot_by_ticker",
            return_value={"PETR4": {"ticker": "PETR4", "score": 81, "sector": "Energy"}},
        ):
            report = poll_service.get_poll_report("PETR4")

        self.assertTrue(report["why_it_matters"])
        self.assertFalse(poll_service.POLL_STORE_PATH.exists())

    def test_load_store_migrates_legacy_poll_payloads(self):
        legacy_store = {
            "polls": {
                "2026-W17:PETR4": {
                    "id": "2026-W17:PETR4",
                    "symbol": "PETR4",
                    "week_key": "2026-W17",
                    "market_type": "stock",
                    "question": "Legacy poll?",
                    "options": [
                        {"key": "A", "label": "Up", "votes": 2},
                        {"key": "B", "label": "Down", "votes": 1},
                    ],
                    "created_at": "2026-04-23T10:00:00Z",
                    "updated_at": "2026-04-23T10:00:00Z",
                }
            }
        }

        poll_service.POLL_STORE_PATH.write_text(
            json.dumps(legacy_store, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        with patch.object(poll_service, "_week_key", return_value="2026-W17"), patch.object(
            poll_service,
            "get_snapshot_by_ticker",
            return_value={"PETR4": {"ticker": "PETR4", "score": 81, "sector": "Energy"}},
        ):
            poll = poll_service.get_weekly_poll("PETR4")

        self.assertEqual(poll["schema_version"], poll_service.POLL_SCHEMA_VERSION)
        self.assertIn("report", poll)
        self.assertIn("context", poll)
        self.assertIn("question_variants", poll)
        self.assertIn("quality", poll)
        saved = json.loads(poll_service.POLL_STORE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            saved["polls"]["2026-W17:PETR4"]["schema_version"],
            poll_service.POLL_SCHEMA_VERSION,
        )

    def test_load_store_keeps_cache_mtime_after_migration(self):
        legacy_store = {
            "polls": {
                "2026-W17:PETR4": {
                    "id": "2026-W17:PETR4",
                    "symbol": "PETR4",
                    "week_key": "2026-W17",
                    "market_type": "stock",
                    "question": "Legacy poll?",
                    "options": [
                        {"key": "A", "label": "Up", "votes": 1},
                        {"key": "B", "label": "Down", "votes": 0},
                    ],
                    "created_at": "2026-04-23T10:00:00Z",
                    "updated_at": "2026-04-23T10:00:00Z",
                }
            }
        }

        poll_service.POLL_STORE_PATH.write_text(
            json.dumps(legacy_store, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        with patch.object(poll_service, "_week_key", return_value="2026-W17"), patch.object(
            poll_service,
            "get_snapshot_by_ticker",
            return_value={"PETR4": {"ticker": "PETR4", "score": 81, "sector": "Energy"}},
        ):
            poll_service.get_weekly_poll("PETR4")

        file_mtime = poll_service.POLL_STORE_PATH.stat().st_mtime
        self.assertEqual(poll_service._store_cache["mtime"], file_mtime)


if __name__ == "__main__":
    unittest.main()
