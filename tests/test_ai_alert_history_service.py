import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from app.services.ai_alert_history_service import get_ai_alert_history_snapshot, persist_ai_alert_history


class AiAlertHistoryServiceTests(unittest.TestCase):
    def _path(self, tmp: str) -> Path:
        return Path(tmp) / "history.json"

    def test_updates_visible_alert_time_from_latest_market_read(self):
        with TemporaryDirectory() as tmp:
            path = self._path(tmp)
            first = persist_ai_alert_history(
                {
                    "radar": [
                        {
                            "ticker": "PETR4",
                            "tool": "radar",
                            "signal": "BUY",
                            "state": "radar_initial",
                            "price": 45.0,
                            "market_data_updated_at": "2026-05-12T13:00:00+00:00",
                            "updated_at": "2026-05-12T13:00:00+00:00",
                        }
                    ]
                },
                now=datetime(2026, 5, 12, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
                path=path,
            )
            second = persist_ai_alert_history(
                {
                    "radar": [
                        {
                            "ticker": "PETR4",
                            "tool": "radar",
                            "signal": "BUY",
                            "state": "radar_initial",
                            "price": 45.9,
                            "market_data_updated_at": "2026-05-12T14:00:00+00:00",
                            "updated_at": "2026-05-12T14:00:00+00:00",
                        }
                    ]
                },
                now=datetime(2026, 5, 12, 11, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
                path=path,
            )

        self.assertEqual(len(first["radar"]), 1)
        self.assertEqual(len(second["radar"]), 1)
        self.assertEqual(second["radar"][0]["detected_at"], "2026-05-12T14:00:00+00:00")
        self.assertEqual(second["radar"][0]["updated_at"], "2026-05-12T13:00:00+00:00")
        self.assertEqual(second["radar"][0]["last_seen_at"], "2026-05-12T14:00:00+00:00")
        self.assertEqual(second["radar"][0]["price"], 45.9)
        self.assertTrue(second["radar"][0]["active"])

    def test_keeps_twenty_visible_alerts_newest_first(self):
        with TemporaryDirectory() as tmp:
            path = self._path(tmp)
            payload = {
                "heat_map": [
                    {
                        "ticker": f"TST{i:02d}",
                        "tool": "heat_map",
                        "signal": "BUY",
                        "state": "strong_buying",
                        "updated_at": f"2026-05-12T13:{i:02d}:00+00:00",
                    }
                    for i in range(22)
                ]
            }
            result = persist_ai_alert_history(
                payload,
                now=datetime(2026, 5, 12, 10, 30, tzinfo=ZoneInfo("America/Sao_Paulo")),
                path=path,
            )

        self.assertEqual(len(result["heat_map"]), 20)
        self.assertEqual(result["heat_map"][0]["ticker"], "TST21")
        self.assertEqual(result["heat_map"][-1]["ticker"], "TST02")

    def test_market_timestamp_drives_detected_time(self):
        with TemporaryDirectory() as tmp:
            result = persist_ai_alert_history(
                {
                    "heat_map": [
                        {
                            "ticker": "F",
                            "tool": "heat_map",
                            "signal": "BUY",
                            "state": "premarket_strength",
                            "detected_at": "2026-05-18T15:23:00+00:00",
                            "market_data_updated_at": "2026-05-18T11:35:00+00:00",
                        }
                    ]
                },
                now=datetime(2026, 5, 18, 12, 23, tzinfo=ZoneInfo("America/Sao_Paulo")),
                path=self._path(tmp),
            )

        self.assertEqual(result["heat_map"][0]["detected_at"], "2026-05-18T11:35:00+00:00")

    def test_resets_history_after_daily_7am_cutoff(self):
        with TemporaryDirectory() as tmp:
            path = self._path(tmp)
            persist_ai_alert_history(
                {
                    "smart_money": [
                        {
                            "ticker": "AAPL",
                            "tool": "smart_money",
                            "signal": "BUY",
                            "state": "absorption_test",
                            "updated_at": "2026-05-12T13:00:00+00:00",
                        }
                    ]
                },
                now=datetime(2026, 5, 12, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
                path=path,
            )
            result = persist_ai_alert_history(
                {
                    "smart_money": [
                        {
                            "ticker": "MSFT",
                            "tool": "smart_money",
                            "signal": "BUY",
                            "state": "absorption_test",
                            "updated_at": "2026-05-13T11:00:00+00:00",
                        }
                    ]
                },
                now=datetime(2026, 5, 13, 8, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
                path=path,
            )

        self.assertEqual([row["ticker"] for row in result["smart_money"]], ["MSFT"])

    def test_public_snapshot_keeps_twenty_visible_rows_newest_first(self):
        with TemporaryDirectory() as tmp:
            path = self._path(tmp)
            persist_ai_alert_history(
                {
                    "heat_map": [
                        {
                            "ticker": f"TST{i:02d}",
                            "tool": "heat_map",
                            "signal": "BUY",
                            "state": "strong_buying",
                            "market_data_updated_at": f"2026-05-18T13:{i:02d}:00+00:00",
                        }
                        for i in range(22)
                    ]
                },
                now=datetime(2026, 5, 18, 12, 30, tzinfo=ZoneInfo("America/Sao_Paulo")),
                path=path,
            )

            snapshot = get_ai_alert_history_snapshot(
                now=datetime(2026, 5, 18, 12, 31, tzinfo=ZoneInfo("America/Sao_Paulo")),
                path=path,
            )

        rows = snapshot["tools"]["heat_map"]
        self.assertEqual(snapshot["max_rows_per_tool"], 20)
        self.assertEqual(len(rows), 20)
        self.assertEqual(rows[0]["ticker"], "TST21")
        self.assertEqual(rows[-1]["ticker"], "TST02")


if __name__ == "__main__":
    unittest.main()
