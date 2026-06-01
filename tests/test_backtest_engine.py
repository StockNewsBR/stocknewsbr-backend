import unittest
from datetime import datetime, timedelta, timezone

from app.portfolio.backtest_engine import backtest_trading_scenarios, replay_trading_scenario


def _make_rows(
    direction: str = "up",
    start: float = 100.0,
    step: float = 0.22,
    base_volume: float = 1000.0,
    breakout_volume: float = 2400.0,
    breakout_body: float = 0.80,
    bars: int = 80,
    breakout_index: int | None = None,
):
    rows = []
    breakout_at = 60 if breakout_index is None and bars >= 68 else max(18, int(bars * 0.62)) if breakout_index is None else breakout_index

    for index in range(bars):
        if direction == "up":
            close = start + (index * step)
            open_price = close - 0.10
            high = close + 0.14
            low = open_price - 0.14
            volume = base_volume + (index % 4) * 25

            if index == breakout_at:
                open_price = close - breakout_body
                high = close + 0.20
                low = open_price - 0.08
                volume = breakout_volume
        else:
            close = start - (index * step)
            open_price = close + 0.10
            high = open_price + 0.14
            low = close - 0.14
            volume = base_volume + (index % 4) * 25

            if index == breakout_at:
                open_price = close + breakout_body
                high = open_price + 0.08
                low = close - 0.20
                volume = breakout_volume

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


def _make_session_close_rows():
    rows = _make_rows(
        "up",
        start=40.0,
        step=0.018,
        base_volume=900,
        breakout_volume=2800,
        breakout_body=0.18,
        bars=42,
        breakout_index=39,
    )
    session_end = datetime(2026, 5, 18, 20, 0, tzinfo=timezone.utc)
    start_time = session_end - timedelta(minutes=5 * (len(rows) - 1))

    for index, row in enumerate(rows):
        row["time"] = (start_time + timedelta(minutes=5 * index)).isoformat()

    return rows


class BacktestEngineTests(unittest.TestCase):
    def test_replay_closes_intraday_long_at_session_end(self):
        result = replay_trading_scenario("ITUB4", _make_session_close_rows(), timeframe="5m")

        self.assertEqual(result["data_quality"]["status"], "valid")
        self.assertTrue(any(event["type"] == "BUY" for event in result["events"]))
        self.assertTrue(any(event["type"] == "SELL" and event["reason"] == "session_close" for event in result["events"]))
        self.assertEqual(result["metrics"]["closed_trades"], 1)

        trade = result["trades"][0]
        self.assertEqual(trade["side"], "long")
        self.assertEqual(trade["status"], "closed")
        self.assertEqual(trade["entry_event_type"], "BUY")
        self.assertEqual(trade["exit_event_type"], "SELL")
        self.assertEqual(trade["exit_reason"], "session_close")
        self.assertIn("max_adverse_excursion_pct", trade)
        self.assertIn("max_favorable_excursion_pct", trade)

    def test_replay_marks_open_short_without_forcing_fake_exit(self):
        result = replay_trading_scenario("AAPL", _make_rows("down"), timeframe="5m")

        self.assertTrue(any(event["type"] == "SHORT" for event in result["events"]))
        self.assertGreaterEqual(result["metrics"]["total_trades"], 1)
        self.assertEqual(result["trades"][0]["side"], "short")
        self.assertIn(result["trades"][0]["status"], {"closed", "open"})
        self.assertIn("marked_return_pct", result["metrics"])

    def test_replay_reports_insufficient_data_without_silent_trade(self):
        result = replay_trading_scenario(
            "PETR4",
            [
                {"time": "bad-1", "close": 0},
                {"time": "bad-2", "open": 10, "high": 10, "low": 9, "close": None},
            ],
            timeframe="5m",
        )

        self.assertEqual(result["data_quality"]["status"], "insufficient_data")
        self.assertEqual(result["data_quality"]["bars_used"], 0)
        self.assertEqual(result["events"], [])
        self.assertEqual(result["trades"], [])
        self.assertEqual(result["metrics"]["total_trades"], 0)

    def test_backtest_trading_scenarios_runs_multiple_symbols_from_local_bars(self):
        result = backtest_trading_scenarios(
            [
                {"symbol": "ITUB4", "ohlc": _make_session_close_rows(), "timeframe": "5m"},
                {"symbol": "AAPL", "bars": _make_rows("down"), "timeframe": "5m"},
            ]
        )

        self.assertEqual(set(result.keys()), {"ITUB4", "AAPL"})
        self.assertGreaterEqual(result["ITUB4"]["metrics"]["closed_trades"], 1)
        self.assertTrue(any(event["type"] == "SHORT" for event in result["AAPL"]["events"]))


if __name__ == "__main__":
    unittest.main()
