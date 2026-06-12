import unittest
from datetime import datetime, timedelta, timezone

from app.portfolio.backtest_engine import (
    analyze_forward_replays,
    compare_replay_scenarios,
    backtest_trading_scenarios,
    forward_test_trading_scenarios,
    replay_trading_scenario,
)


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


def _make_choppy_rows(bars: int = 120):
    rows = []
    price = 100.0
    deltas = [0.08, 0.12, -0.10, -0.14, -0.08, -0.12, 0.10, 0.14]

    for index in range(bars):
        phase = index % len(deltas)
        open_price = price
        close = price + deltas[phase]
        high = max(open_price, close) + (0.22 if phase in {1, 6} else 0.08)
        low = min(open_price, close) - (0.22 if phase in {3, 4} else 0.08)
        volume = 1600.0 if phase in {1, 3, 6} else 900.0

        rows.append(
            {
                "time": f"c{index:03d}",
                "open": round(open_price, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close, 4),
                "volume": volume,
            }
        )
        price = close

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
        self.assertEqual(trade["entry_chart_regime_state"], "trend_up")
        self.assertIn("max_adverse_excursion_pct", trade)
        self.assertIn("max_favorable_excursion_pct", trade)
        self.assertEqual(result["overtrading"]["status"], "ok")
        self.assertIn("trend_up", result["regime_metrics"])

    def test_replay_marks_open_short_without_forcing_fake_exit(self):
        result = replay_trading_scenario("AAPL", _make_rows("down"), timeframe="5m")

        self.assertTrue(any(event["type"] == "SHORT" for event in result["events"]))
        self.assertGreaterEqual(result["metrics"]["total_trades"], 1)
        self.assertEqual(result["trades"][0]["side"], "short")
        self.assertIn(result["trades"][0]["status"], {"closed", "open"})
        self.assertIn("marked_return_pct", result["metrics"])
        self.assertEqual(result["trades"][0]["entry_chart_regime_state"], "trend_down")
        self.assertIn("trend_down", result["regime_metrics"])

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

    def test_replay_tracks_lateral_regime_without_promoting_watch_to_trade(self):
        result = replay_trading_scenario("PETR4", _make_choppy_rows(), timeframe="5m")

        self.assertIn(result["context"].get("chart_regime_state"), {"chop", "range", "squeeze"})
        self.assertEqual(result["trend"], "sideways")
        self.assertEqual(result["events"], [])
        self.assertEqual(result["trades"], [])
        self.assertEqual(result["overtrading"]["status"], "no_trades")
        self.assertGreater(
            sum(result["regime_bar_counts"].get(state, 0) for state in ("chop", "range", "squeeze")),
            0,
        )

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

    def test_forward_test_groups_symbols_and_entry_regimes(self):
        result = forward_test_trading_scenarios(
            [
                {"symbol": "ITUB4", "ohlc": _make_session_close_rows(), "timeframe": "5m"},
                {"symbol": "AAPL", "bars": _make_rows("down"), "timeframe": "5m"},
                {"symbol": "PETR4", "bars": _make_choppy_rows(), "timeframe": "5m"},
            ]
        )

        analysis = result["analysis"]
        self.assertEqual(result["type"], "forward_test")
        self.assertEqual(analysis["symbols_tested"], 3)
        self.assertIn("trend_up", analysis["regime_metrics"])
        self.assertIn("trend_down", analysis["regime_metrics"])
        self.assertEqual(analysis["symbols"]["PETR4"]["overtrading"]["status"], "no_trades")
        self.assertEqual(analysis["overtrading"]["status"], "ok")

    def test_forward_analysis_flags_lateral_overtrading_from_saved_replay_log(self):
        analysis = analyze_forward_replays(
            {
                "LAT": {
                    "symbol": "LAT",
                    "data_quality": {"bars_used": 60},
                    "regime_bar_counts": {"range": 40, "trend_up": 20},
                    "trades": [
                        {
                            "side": "long",
                            "status": "closed",
                            "entry_chart_regime_state": "range",
                            "pnl_pct": -0.20,
                            "bars_held": 2,
                        },
                        {
                            "side": "short",
                            "status": "closed",
                            "entry_chart_regime_state": "range",
                            "pnl_pct": -0.10,
                            "bars_held": 2,
                        },
                        {
                            "side": "long",
                            "status": "closed",
                            "entry_chart_regime_state": "range",
                            "pnl_pct": -0.05,
                            "bars_held": 1,
                        },
                    ],
                }
            }
        )

        self.assertEqual(analysis["overtrading"]["status"], "overtrading")
        self.assertEqual(analysis["overtrading"]["lateral_trades"], 3)
        self.assertGreater(analysis["overtrading"]["lateral_entry_rate_per_100_bars"], 4.0)
        self.assertEqual(analysis["regime_metrics"]["range"]["bucket"], "lateral")

    def test_compare_replay_scenarios_reports_missed_trades_early_exits_and_watch_reduction(self):
        reference = {
            "trades": [
                {
                    "side": "long",
                    "entry_time": "2026-06-01T10:00:00+00:00",
                    "entry_price": 100.0,
                    "entry_event_type": "BUY",
                    "bars_held": 8,
                    "exit_reason": "target",
                    "pnl_pct": 3.2,
                },
                {
                    "side": "short",
                    "entry_time": "2026-06-01T11:00:00+00:00",
                    "entry_price": 105.0,
                    "entry_event_type": "SHORT",
                    "bars_held": 5,
                    "exit_reason": "stop",
                    "pnl_pct": -1.1,
                },
            ],
            "watch_signals": {"count": 6},
        }
        current = {
            "trades": [
                {
                    "side": "long",
                    "entry_time": "2026-06-01T10:00:00+00:00",
                    "entry_price": 100.0,
                    "entry_event_type": "BUY",
                    "bars_held": 4,
                    "exit_reason": "session_close",
                    "pnl_pct": 1.5,
                }
            ],
            "watch_signals": {"count": 2},
        }

        comparison = compare_replay_scenarios(reference, current)

        self.assertEqual(comparison["matched_trades"], 1)
        self.assertEqual(comparison["missed_trades"], 1)
        self.assertEqual(comparison["early_exits"], 1)
        self.assertEqual(comparison["watch_reduction"], 4)
        self.assertEqual(comparison["reference_watch_signals"], 6)
        self.assertEqual(comparison["current_watch_signals"], 2)


if __name__ == "__main__":
    unittest.main()
