import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

try:
    from app.services import poll_service
    from app.data.us_economic_calendar_2026 import events_in_window
    IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    IMPORT_ERROR = exc


# Deterministic reference instants (poll window = Sunday 00:00 -> Thursday 24:00 UTC).
QUIET_WEEK_NOW = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)  # Tue; no econ events that week
ECON_WEEK_NOW = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)  # Mon; Durable Goods 27/07 etc.
CLAIMS_WEEK_NOW = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)  # Mon; only weekly jobless claims Thu 20/08
FRIDAY_NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)  # Friday: outside the window


@unittest.skipIf(IMPORT_ERROR is not None, f"runtime dependency unavailable: {IMPORT_ERROR}")
class PollServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.original_path = poll_service.POLL_STORE_PATH
        poll_service.POLL_STORE_PATH = Path(self.temp_dir) / "weekly_polls.json"
        poll_service._earnings_cache.clear()

    def tearDown(self):
        poll_service.POLL_STORE_PATH = self.original_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _at(self, now):
        return patch.object(poll_service, "_utc_now", return_value=now)

    def _no_yfinance(self):
        return patch.object(poll_service, "_fetch_earnings_date", return_value=None)

    # ----------------------------------------------------------------- #
    # Policy: earnings poll
    # ----------------------------------------------------------------- #
    def test_earnings_in_window_creates_earnings_poll(self):
        signal = {"ticker": "VALE3", "score": 72, "earnings_date": "2026-06-10", "sector": "Materials"}

        with self._at(QUIET_WEEK_NOW):
            poll = poll_service.ensure_weekly_poll("VALE3", signal=signal)

        self.assertIsNotNone(poll)
        self.assertEqual(poll["event_type"], "earnings")
        self.assertEqual(poll["event_date"], "2026-06-10")
        self.assertEqual(poll["question"], "Anúncio do trimestre em 10/06/2026")
        labels = [option["label"] for option in poll["options"]]
        self.assertEqual(labels, ["Vai bater os números e subir", "Não vai bater e cair"])
        self.assertTrue(poll["earnings_week"])
        self.assertEqual(poll["timing_bucket"], "earnings_week")
        self.assertEqual(poll["report"]["event_type"], "earnings")

    def test_earnings_outside_window_is_not_earnings_poll(self):
        # Friday 12/06 is outside the Sunday->Thursday window; no econ event either -> no poll.
        signal = {"ticker": "VALE3", "score": 72, "earnings_date": "2026-06-12"}

        with self._at(QUIET_WEEK_NOW), self._no_yfinance():
            poll = poll_service.ensure_weekly_poll("VALE3", signal=signal)

        self.assertIsNone(poll)

    def test_earnings_uses_yfinance_lookup_when_signal_has_no_date(self):
        earnings_dt = datetime(2026, 6, 10, tzinfo=UTC)

        with self._at(QUIET_WEEK_NOW), patch.object(
            poll_service, "_fetch_earnings_date", return_value=earnings_dt
        ):
            poll = poll_service.ensure_weekly_poll("AAPL", signal={"ticker": "AAPL", "score": 90})

        self.assertIsNotNone(poll)
        self.assertEqual(poll["event_type"], "earnings")
        self.assertEqual(poll["event_source"], "yfinance_calendar")

    # ----------------------------------------------------------------- #
    # Policy: economic calendar poll
    # ----------------------------------------------------------------- #
    def test_econ_event_in_window_creates_event_poll(self):
        with self._at(ECON_WEEK_NOW), self._no_yfinance():
            poll = poll_service.ensure_weekly_poll("PETR4", signal={"ticker": "PETR4", "score": 80})

        self.assertIsNotNone(poll)
        self.assertEqual(poll["event_type"], "economic_calendar")
        self.assertEqual(poll["event_name"], "Durable Goods")
        self.assertEqual(poll["event_date"], "2026-07-27")
        self.assertIn("Durable Goods", poll["question"])
        self.assertIn("27/07/2026", poll["question"])
        labels = [option["label"] for option in poll["options"]]
        self.assertEqual(labels, ["Acima do esperado", "Abaixo do esperado"])

    def test_econ_event_applies_to_crypto_symbols_too(self):
        with self._at(ECON_WEEK_NOW):
            poll = poll_service.ensure_weekly_poll("BTCUSDT", market_type="crypto")

        self.assertIsNotNone(poll)
        self.assertEqual(poll["event_type"], "economic_calendar")
        self.assertEqual(poll["market_type"], "crypto")

    def test_weekly_jobless_claims_generate_event(self):
        with self._at(CLAIMS_WEEK_NOW), self._no_yfinance():
            poll = poll_service.ensure_weekly_poll("PETR4")

        self.assertIsNotNone(poll)
        self.assertEqual(poll["event_name"], "Initial Jobless Claims")
        self.assertEqual(poll["event_date"], "2026-08-20")

    def test_earnings_takes_precedence_over_econ_event(self):
        signal = {"ticker": "VALE3", "earnings_date": "2026-07-28"}

        with self._at(ECON_WEEK_NOW):
            poll = poll_service.ensure_weekly_poll("VALE3", signal=signal)

        self.assertEqual(poll["event_type"], "earnings")

    # ----------------------------------------------------------------- #
    # Policy: neither event -> no poll, generic never created
    # ----------------------------------------------------------------- #
    def test_no_event_in_window_creates_no_poll(self):
        with self._at(QUIET_WEEK_NOW), self._no_yfinance():
            poll = poll_service.ensure_weekly_poll("PETR4", signal={"ticker": "PETR4", "score": 88})

        self.assertIsNone(poll)
        self.assertFalse(poll_service.POLL_STORE_PATH.exists())

    def test_generic_poll_never_created_even_with_rich_trend_signal(self):
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

        with self._at(QUIET_WEEK_NOW), self._no_yfinance():
            poll = poll_service.ensure_weekly_poll("PETR4", signal=signal)
            with patch.object(poll_service, "get_snapshot_by_ticker", return_value={"PETR4": signal}):
                payload = poll_service.get_weekly_poll("PETR4")

        self.assertIsNone(poll)
        self.assertEqual(payload["status"], "none")
        self.assertEqual(payload["question"], "")
        self.assertEqual(payload["options"], [])

    def test_no_poll_outside_sunday_thursday_window(self):
        # Poll created Monday, gone on Friday of the same week.
        with self._at(ECON_WEEK_NOW):
            created = poll_service.ensure_weekly_poll("PETR4")
        self.assertIsNotNone(created)

        with self._at(FRIDAY_NOW), self._no_yfinance(), patch.object(
            poll_service, "get_snapshot_by_ticker", return_value={}
        ):
            payload = poll_service.get_weekly_poll("PETR4")

        self.assertEqual(payload["status"], "none")

    def test_legacy_generic_stored_poll_is_not_served(self):
        week_key = poll_service._week_key(QUIET_WEEK_NOW)
        legacy_store = {
            "polls": {
                f"{week_key}:PETR4": {
                    "id": f"{week_key}:PETR4",
                    "symbol": "PETR4",
                    "week_key": week_key,
                    "market_type": "stock",
                    "question": "PETR4 vai subir ou cair?",
                    "options": [
                        {"key": "A", "label": "Sobe", "votes": 2},
                        {"key": "B", "label": "Cai", "votes": 1},
                    ],
                    "created_at": "2026-06-07T10:00:00+00:00",
                }
            }
        }
        poll_service.POLL_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        poll_service.POLL_STORE_PATH.write_text(
            json.dumps(legacy_store, ensure_ascii=False), encoding="utf-8"
        )

        with self._at(QUIET_WEEK_NOW), self._no_yfinance(), patch.object(
            poll_service, "get_snapshot_by_ticker", return_value={}
        ):
            payload = poll_service.get_weekly_poll("PETR4")

        self.assertEqual(payload["status"], "none")
        self.assertEqual(payload["question"], "")

    # ----------------------------------------------------------------- #
    # Votes / idempotency
    # ----------------------------------------------------------------- #
    def test_vote_replaces_previous_vote(self):
        with self._at(ECON_WEEK_NOW), patch.object(
            poll_service, "get_snapshot_by_ticker", return_value={}
        ):
            poll_service.ensure_weekly_poll("BTCUSDT", market_type="crypto")
            poll = poll_service.vote_poll("BTCUSDT", "A", user_id=10)
            poll = poll_service.vote_poll("BTCUSDT", "B", user_id=10)

        option_a = next(item for item in poll["options"] if item["key"] == "A")
        option_b = next(item for item in poll["options"] if item["key"] == "B")

        self.assertEqual(option_a["votes"], 0)
        self.assertEqual(option_b["votes"], 1)

    def test_vote_without_active_poll_raises(self):
        with self._at(QUIET_WEEK_NOW), self._no_yfinance(), patch.object(
            poll_service, "get_snapshot_by_ticker", return_value={}
        ):
            with self.assertRaises(ValueError):
                poll_service.vote_poll("PETR4", "A", user_id=1)

    def test_ensure_is_idempotent_and_preserves_votes(self):
        with self._at(ECON_WEEK_NOW), patch.object(
            poll_service, "get_snapshot_by_ticker", return_value={}
        ):
            first = poll_service.ensure_weekly_poll("BTCUSDT", market_type="crypto")
            poll_service.vote_poll("BTCUSDT", "A", user_id=7)
            second = poll_service.ensure_weekly_poll("BTCUSDT", market_type="crypto")

        self.assertEqual(first["id"], second["id"])
        option_a = next(item for item in second["options"] if item["key"] == "A")
        self.assertEqual(option_a["votes"], 1)

    # ----------------------------------------------------------------- #
    # Batch generation / report
    # ----------------------------------------------------------------- #
    def test_generate_weekly_polls_is_bounded_and_event_driven(self):
        snapshot = {
            "BTCUSDT": {"ticker": "BTCUSDT", "symbol": "BTCUSDT", "score": 99},
            "PETR4": {"ticker": "PETR4", "symbol": "PETR4", "score": 85, "sector": "Energy"},
            "VALE3": {"ticker": "VALE3", "symbol": "VALE3", "score": 83, "sector": "Materials"},
        }

        with self._at(ECON_WEEK_NOW), self._no_yfinance(), patch.object(
            poll_service, "get_snapshot_by_ticker", return_value=snapshot
        ):
            created = poll_service.generate_weekly_polls_for_top_symbols(limit=2)

        self.assertEqual(len(created), 2)
        self.assertTrue(all(poll["event_type"] == "economic_calendar" for poll in created))

    def test_generate_weekly_polls_returns_empty_without_events(self):
        snapshot = {
            "PETR4": {"ticker": "PETR4", "symbol": "PETR4", "score": 85},
            "BTCUSDT": {"ticker": "BTCUSDT", "symbol": "BTCUSDT", "score": 99},
        }

        with self._at(QUIET_WEEK_NOW), self._no_yfinance(), patch.object(
            poll_service, "get_snapshot_by_ticker", return_value=snapshot
        ):
            created = poll_service.generate_weekly_polls_for_top_symbols(limit=5)

        self.assertEqual(created, [])
        self.assertFalse(poll_service.POLL_STORE_PATH.exists())

    def test_poll_report_reflects_active_poll_or_none(self):
        with self._at(ECON_WEEK_NOW), self._no_yfinance(), patch.object(
            poll_service, "get_snapshot_by_ticker", return_value={"PETR4": {"ticker": "PETR4", "score": 80}}
        ):
            report = poll_service.get_poll_report("PETR4")
        self.assertEqual(report["event_type"], "economic_calendar")
        self.assertEqual(len(report["options"]), 2)

        with self._at(QUIET_WEEK_NOW), self._no_yfinance(), patch.object(
            poll_service, "get_snapshot_by_ticker", return_value={}
        ):
            empty_report = poll_service.get_poll_report("ITUB4")
        self.assertEqual(empty_report["status"], "none")
        self.assertEqual(empty_report["options"], [])

    # ----------------------------------------------------------------- #
    # Calendar data helper
    # ----------------------------------------------------------------- #
    def test_events_in_window_sorted_with_weekly_claims(self):
        start = datetime(2026, 7, 26, tzinfo=UTC)
        end = datetime(2026, 7, 31, tzinfo=UTC)

        events = events_in_window(start, end)

        names = [event["name"] for event in events]
        self.assertEqual(names[0], "Durable Goods")
        self.assertIn("Decisão do FOMC", names)
        self.assertIn("Initial Jobless Claims", names)
        dates = [event["date"] for event in events]
        self.assertEqual(dates, sorted(dates))
        self.assertTrue(
            all(start.date().isoformat() <= item < end.date().isoformat() for item in dates)
        )


if __name__ == "__main__":
    unittest.main()
