import unittest

try:
    from app.engine.trend_breakout_signal_engine import build_trend_breakout_payload
    IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    IMPORT_ERROR = exc


def _make_rows(direction: str = "up"):
    rows = []
    close = 100.0

    for index in range(80):
        if direction == "up":
            close = 100.0 + (index * 0.22)
            open_price = close - 0.10
            high = close + 0.14
            low = open_price - 0.14
            volume = 1000 + (index % 4) * 25

            if index == 60:
                open_price = close - 0.80
                high = close + 0.20
                low = open_price - 0.08
                volume = 2400
        else:
            close = 140.0 - (index * 0.24)
            open_price = close + 0.10
            high = open_price + 0.14
            low = close - 0.14
            volume = 1000 + (index % 4) * 25

            if index == 60:
                open_price = close + 0.80
                high = open_price + 0.08
                low = close - 0.20
                volume = 2400

        rows.append(
            {
                "time": f"t{index:03d}",
                "open": round(open_price, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close, 4),
                "volume": float(volume),
            }
        )

    return rows


@unittest.skipIf(IMPORT_ERROR is not None, f"runtime dependency unavailable: {IMPORT_ERROR}")
class TrendBreakoutSignalEngineTests(unittest.TestCase):
    def test_generates_buy_event_for_brazilian_stock_chart(self):
        payload = build_trend_breakout_payload("PETR4", _make_rows("up"), timeframe="5m")

        self.assertEqual(payload["ticker"], "PETR4")
        self.assertIn(payload["profile"], {"b3_stock", "bdr", "us_stock"})
        self.assertTrue(any(event["type"] == "BUY" for event in payload["events"]))

    def test_generates_short_event_for_us_stock_chart(self):
        payload = build_trend_breakout_payload("AAPL", _make_rows("down"), timeframe="5m")

        self.assertEqual(payload["ticker"], "AAPL")
        self.assertEqual(payload["profile"], "us_stock")
        self.assertTrue(any(event["type"] == "SHORT" for event in payload["events"]))


if __name__ == "__main__":
    unittest.main()
