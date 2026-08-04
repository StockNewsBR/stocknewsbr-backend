import unittest

import pandas as pd

from app.engine.events.price_event_engine import detect_price_events


def _make_frame(start: str, closes: list[float]):
    index = pd.date_range(start=start, periods=len(closes), freq="5min", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [value - 0.05 for value in closes],
            "High": [value + 0.10 for value in closes],
            "Low": [value - 0.10 for value in closes],
            "Close": closes,
            "Volume": [1000] * (len(closes) - 3) + [1800, 2100, 2600],
        },
        index=index,
    )


class PriceEventEngineTests(unittest.TestCase):
    def test_detects_buy_event_during_regular_b3_session(self):
        closes = [10.0] * 20 + [10.05, 10.08, 10.12, 10.18, 10.45, 10.70]
        pool = {"PETR4.SA": _make_frame("2026-04-13 13:00:00+00:00", closes)}
        ranked = [{"ticker": "PETR4", "score": 84, "trend": "Alta"}]

        events = detect_price_events(pool, ranked)

        self.assertTrue(events)
        self.assertEqual(events[0]["type"], "BUY")
        self.assertEqual(events[0]["ticker"], "PETR4")

    def test_filters_b3_events_outside_regular_session(self):
        closes = [10.0] * 20 + [10.05, 10.08, 10.12, 10.18, 10.45, 10.70]
        pool = {"PETR4.SA": _make_frame("2026-04-13 23:00:00+00:00", closes)}
        ranked = [{"ticker": "PETR4", "score": 84, "trend": "Alta"}]

        events = detect_price_events(pool, ranked)

        self.assertEqual(events, [])

    def test_only_scans_ranked_symbols_when_ranked_rows_are_provided(self):
        closes = [10.0] * 20 + [10.05, 10.08, 10.12, 10.18, 10.45, 10.70]
        pool = {
            "PETR4.SA": _make_frame("2026-04-13 13:00:00+00:00", closes),
            "VALE3.SA": _make_frame("2026-04-13 13:00:00+00:00", closes),
        }
        ranked = [{"ticker": "PETR4", "score": 84, "trend": "Alta"}]

        events = detect_price_events(pool, ranked)

        self.assertTrue(events)
        self.assertEqual(sorted({event["ticker"] for event in events}), ["PETR4"])


if __name__ == "__main__":
    unittest.main()
