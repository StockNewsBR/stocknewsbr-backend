"""Mission 70 — P0.3: granularity-aware freshness for AI-tools rows.

A daily/session finding is stamped with the daily-bar close timestamp, which is
many hours old the instant the session ends and stays that way all weekend.
Judging it against the intraday 900s TTL wrongly marks Friday's close HISTORICAL
on Saturday. These tests pin the corrected behaviour with a frozen clock so they
are deterministic on any day (they run on a Saturday today).
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.services import public_ai_tools_service as svc


# Anchor times (UTC). BRT = UTC-3, B3 close 17:55 BRT == 20:55 UTC.
SATURDAY = datetime(2026, 7, 25, 13, 30, tzinfo=timezone.utc)          # 10:30 BRT, weekend
MONDAY_PRE_OPEN = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)     # 09:00 BRT, before close
MONDAY_POST_CLOSE = datetime(2026, 7, 27, 21, 0, tzinfo=timezone.utc)   # 18:00 BRT, after close
FRIDAY_CLOSE_AS_OF = "2026-07-24T20:05:00+00:00"                        # Friday daily-bar close


def _row(timeframe="1D", as_of=FRIDAY_CLOSE_AS_OF, **extra):
    row = {
        "state": "low_risk",
        "ticker": "PETR4",
        "symbol": "PETR4",
        "tool": "risk",
        "score": 88.0,
        "score_source_scale": "0_100",
        "master_score": 88.0,
        "timeframe": timeframe,
        "signal": "BUY",
        "trade_action": "BUY",
        "decision_ready": True,
        "can_trade": True,
        "audit_status": "APPROVED",
        "price": 37.5,
        "volume": 1_000_000,
        "data_quality": "real_time",
        "as_of": as_of,
        "updated_at": as_of,
        "last_confirmed_at": as_of,
    }
    row.update(extra)
    return row


class RowFreshnessUnitTests(unittest.TestCase):
    def test_daily_bar_is_fresh_on_weekend(self):
        with patch.object(svc, "_now_utc", return_value=SATURDAY):
            result = svc._row_freshness(_row(timeframe="1D"))
        self.assertFalse(result["stale"])
        self.assertEqual(result["basis"], "daily_session")
        self.assertEqual(result["reason"], "latest_completed_session")

    def test_daily_bar_fresh_monday_before_open(self):
        with patch.object(svc, "_now_utc", return_value=MONDAY_PRE_OPEN):
            self.assertFalse(svc._row_is_stale(_row(timeframe="1D")))

    def test_daily_bar_superseded_after_a_newer_session_closes(self):
        with patch.object(svc, "_now_utc", return_value=MONDAY_POST_CLOSE):
            result = svc._row_freshness(_row(timeframe="1D"))
        self.assertTrue(result["stale"])
        self.assertEqual(result["reason"], "superseded_by_newer_session")

    def test_intraday_fresh_within_ttl(self):
        recent = "2026-07-25T13:25:00+00:00"  # 5 min before SATURDAY
        with patch.object(svc, "_now_utc", return_value=SATURDAY):
            result = svc._row_freshness(_row(timeframe="5M", as_of=recent))
        self.assertFalse(result["stale"])
        self.assertEqual(result["basis"], "intraday_ttl")

    def test_intraday_stale_beyond_ttl(self):
        with patch.object(svc, "_now_utc", return_value=SATURDAY):
            result = svc._row_freshness(_row(timeframe="15M", as_of=FRIDAY_CLOSE_AS_OF))
        self.assertTrue(result["stale"])
        self.assertEqual(result["reason"], "intraday_ttl_expired")

    def test_ambiguous_month_token_is_treated_as_daily_not_minute(self):
        # "1M" is a month-range token here, not one minute -> daily window, fresh.
        with patch.object(svc, "_now_utc", return_value=SATURDAY):
            result = svc._row_freshness(_row(timeframe="1M"))
        self.assertFalse(result["stale"])
        self.assertEqual(result["basis"], "daily_session")

    def test_explicit_stale_flag_always_wins(self):
        with patch.object(svc, "_now_utc", return_value=SATURDAY):
            self.assertTrue(svc._row_is_stale(_row(timeframe="1D", is_stale=True)))

    def test_missing_as_of_is_not_falsely_staled(self):
        row = _row(timeframe="1D")
        row["as_of"] = ""
        with patch.object(svc, "_now_utc", return_value=SATURDAY):
            result = svc._row_freshness(row)
        self.assertFalse(result["stale"])
        self.assertEqual(result["reason"], "no_as_of")


class PayloadIntegrationTests(unittest.TestCase):
    def _snapshot(self, rows):
        return {
            "ai_tools": {"risk": rows, "flow": [], "liquidity": [], "trend": [],
                         "momentum": [], "smart_money": [], "news": []},
            "generated_at": SATURDAY.isoformat(),
            "updated_at": SATURDAY.isoformat(),
            "source": "engine",
            "stale": False,
        }

    def test_weekend_daily_rows_render_ready_not_historical(self):
        snapshot = self._snapshot([_row(timeframe="1D")])
        context = {
            "analyzed_at": SATURDAY.isoformat(), "symbols": (), "selected_symbol": None,
            "selected_tool": None, "timeframe": None,
        }
        with patch.object(svc, "_now_utc", return_value=SATURDAY):
            payload = svc._payload_from_snapshot(snapshot, snapshot["ai_tools"], context=context, using_fallback=False)
        self.assertEqual(payload["status"], "READY")
        self.assertEqual(payload["displayable_count"], 1)
        row = payload["tools"]["risk"][0]
        self.assertEqual(row["freshness_status"], "READY")
        self.assertEqual(row["freshness_basis"], "daily_session")
        self.assertEqual(row["source_as_of"], FRIDAY_CLOSE_AS_OF)
        self.assertTrue(row["evaluated_at"])

    def test_weekend_intraday_rows_stay_historical(self):
        snapshot = self._snapshot([_row(timeframe="15M")])
        context = {
            "analyzed_at": SATURDAY.isoformat(), "symbols": (), "selected_symbol": None,
            "selected_tool": None, "timeframe": None,
        }
        with patch.object(svc, "_now_utc", return_value=SATURDAY):
            payload = svc._payload_from_snapshot(snapshot, snapshot["ai_tools"], context=context, using_fallback=False)
        self.assertEqual(payload["status"], "HISTORICAL")
        self.assertEqual(payload["displayable_count"], 0)
        self.assertEqual(len(payload["historical_tools"]["risk"]), 1)


if __name__ == "__main__":
    unittest.main()
