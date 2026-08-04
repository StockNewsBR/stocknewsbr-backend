import unittest
from datetime import datetime, timedelta, timezone

try:
    from app.engine.trend_breakout_signal_engine import build_trend_breakout_payload
    IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    IMPORT_ERROR = exc


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
    close = start
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


def _make_early_uptrend_rows():
    rows = []
    close = 49.3
    for index in range(12):
        close += 0.005 if index % 2 else -0.004
        rows.append(
            {
                "time": f"t{index:03d}",
                "open": round(close - 0.01, 4),
                "high": round(close + 0.03, 4),
                "low": round(close - 0.04, 4),
                "close": round(close, 4),
                "volume": 900.0,
            }
        )
    for index in range(12, 30):
        close += 0.08
        rows.append(
            {
                "time": f"t{index:03d}",
                "open": round(close - 0.06, 4),
                "high": round(close + 0.04, 4),
                "low": round(close - 0.08, 4),
                "close": round(close, 4),
                "volume": 1800.0 if index == 12 else 1200.0,
            }
        )
    return rows


def _make_resistance_reclaim_rows():
    rows = []
    close = 20.8
    for index in range(18):
        close -= 0.035
        rows.append(
            {
                "time": f"t{index:03d}",
                "open": round(close + 0.02, 4),
                "high": round(close + 0.04, 4),
                "low": round(close - 0.04, 4),
                "close": round(close, 4),
                "volume": float(1000 + (index % 3) * 20),
            }
        )
    for index in range(18, 32):
        close = 20.15 + (index - 18) * 0.012
        rows.append(
            {
                "time": f"t{index:03d}",
                "open": round(close - 0.015, 4),
                "high": round(close + 0.035, 4),
                "low": round(close - 0.04, 4),
                "close": round(close, 4),
                "volume": float(950 + (index % 4) * 15),
            }
        )
    for index in range(32, 45):
        close += 0.045
        body = 0.035 if index < 40 else 0.075
        rows.append(
            {
                "time": f"t{index:03d}",
                "open": round(close - body, 4),
                "high": round(close + 0.035, 4),
                "low": round(close - body - 0.025, 4),
                "close": round(close, 4),
                "volume": 1800.0 if index >= 39 else 1200.0,
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
        short_event = next(event for event in payload["events"] if event["type"] == "SHORT")
        self.assertGreaterEqual(short_event["confidence"], 50)
        self.assertIn(short_event["chart_regime_state"], {"trend_down", "breakout_down"})
        self.assertIn("short_confidence", payload["context"])

    def test_short_b3_intraday_window_can_generate_operational_entry(self):
        payload = build_trend_breakout_payload(
            "ITUB4",
            _make_rows(
                "up",
                start=40.0,
                step=0.018,
                base_volume=900,
                breakout_volume=2600,
                breakout_body=0.16,
                bars=45,
            ),
            timeframe="5m",
        )

        self.assertNotEqual(payload["context"].get("reason"), "insufficient_data")
        self.assertLess(payload["context"]["warmup_bars"], 45)
        self.assertTrue(any(event["type"] == "BUY" for event in payload["events"]))
        buy_event = next(event for event in payload["events"] if event["type"] == "BUY")
        self.assertIn(buy_event["reason"], {"breakout", "trend_continuation", "trend_acceptance", "pullback_resume", "liquidity_reversal"})

    def test_marks_early_buy_when_intraday_uptrend_starts_after_open(self):
        payload = build_trend_breakout_payload("PETR3", _make_early_uptrend_rows(), timeframe="5m")

        buy_events = [event for event in payload["events"] if event["type"] == "BUY"]

        self.assertLessEqual(payload["context"]["warmup_bars"], 12)
        self.assertTrue(buy_events)
        self.assertIn(buy_events[0]["reason"], {"trend_acceptance", "trend_continuation", "breakout"})

    def test_resistance_breakout_is_long_not_short(self):
        payload = build_trend_breakout_payload("BBAS3", _make_resistance_reclaim_rows(), timeframe="5m")

        first_entry = next(event for event in payload["events"] if event["type"] in {"BUY", "SHORT"})

        self.assertEqual(first_entry["type"], "BUY")
        self.assertNotEqual(first_entry["type"], "SHORT")
        self.assertGreaterEqual(payload["context"]["long_confidence"], payload["context"]["short_confidence"])

    def test_bearish_continuation_stays_short_instead_of_early_cover(self):
        payload = build_trend_breakout_payload(
            "PETR4",
            _make_rows("down", start=45.8, step=0.025, base_volume=1200, breakout_volume=2600, breakout_body=0.18),
            timeframe="5m",
            ai_context={
                "market_regime": {"state": "bear_trend", "score": 84},
                "smart_money": {"state": "retail_noise", "score": 22},
                "institutional_flow": {"state": "distribution_risk", "score": 18},
                "master_score": {"state": "bearish", "score": 88},
            },
        )

        self.assertIn(payload["signal"], {"SHORT", "WATCH_SHORT", "COVER", "NEUTRAL"})
        self.assertGreaterEqual(payload["context"]["short_confidence"], payload["context"]["long_confidence"])
        if payload["events"]:
            self.assertNotEqual(payload["events"][-1]["reason"], "protect_profit")

    def test_short_exits_when_resistance_break_invalidates_trade(self):
        rows = _make_rows(
            "down",
            start=100.0,
            step=0.035,
            base_volume=1200,
            breakout_volume=3000,
            breakout_body=0.28,
            bars=62,
            breakout_index=35,
        )[:38]
        close = rows[-1]["close"]
        for jump in [0.8, 1.0, 1.2]:
            close += jump
            index = len(rows)
            rows.append(
                {
                    "time": f"t{index:03d}",
                    "open": round(close - jump * 0.65, 4),
                    "high": round(close + jump * 0.2, 4),
                    "low": round(close - jump * 0.75, 4),
                    "close": round(close, 4),
                    "volume": 3000.0,
                }
            )

        payload = build_trend_breakout_payload("TSLA", rows, timeframe="5m")
        cover_events = [event for event in payload["events"] if event["type"] == "COVER"]

        self.assertTrue(cover_events)
        self.assertEqual(cover_events[0]["reason"], "resistance_break")

    def test_short_exits_on_structural_resistance_break_with_muted_volume(self):
        rows = _make_rows(
            "down",
            start=100.0,
            step=0.035,
            base_volume=1200,
            breakout_volume=3000,
            breakout_body=0.28,
            bars=62,
            breakout_index=35,
        )[:38]
        close = rows[-1]["close"]
        for jump in [0.55, 0.65, 0.75]:
            close += jump
            index = len(rows)
            rows.append(
                {
                    "time": f"t{index:03d}",
                    "open": round(close - jump * 0.55, 4),
                    "high": round(close + jump * 0.16, 4),
                    "low": round(close - jump * 0.65, 4),
                    "close": round(close, 4),
                    "volume": 650.0,
                }
            )

        payload = build_trend_breakout_payload("TSLA", rows, timeframe="5m")
        cover_events = [event for event in payload["events"] if event["type"] == "COVER"]

        self.assertTrue(cover_events)
        self.assertEqual(cover_events[0]["reason"], "resistance_break")

    def test_long_exits_on_structural_support_break_with_muted_volume(self):
        rows = _make_rows(
            "up",
            start=50.0,
            step=0.035,
            base_volume=1200,
            breakout_volume=3000,
            breakout_body=0.28,
            bars=62,
            breakout_index=35,
        )[:38]
        close = rows[-1]["close"]
        for drop in [0.55, 0.65, 0.75]:
            close -= drop
            index = len(rows)
            rows.append(
                {
                    "time": f"t{index:03d}",
                    "open": round(close + drop * 0.55, 4),
                    "high": round(close + drop * 0.65, 4),
                    "low": round(close - drop * 0.16, 4),
                    "close": round(close, 4),
                    "volume": 650.0,
                }
            )

        payload = build_trend_breakout_payload("PETR4", rows, timeframe="5m")
        sell_events = [event for event in payload["events"] if event["type"] == "SELL"]

        self.assertTrue(sell_events)
        self.assertEqual(sell_events[0]["reason"], "support_break")

    def test_bearish_ai_context_blocks_long_entry(self):
        payload = build_trend_breakout_payload(
            "PETR4",
            _make_rows("up"),
            timeframe="5m",
            ai_context={
                "market_regime": {"state": "bear_trend", "score": 82},
                "smart_money": {"state": "retail_noise", "score": 22},
                "master_score": {"state": "weak_setup", "score": 32},
            },
        )

        self.assertEqual(payload["signal"], "NEUTRAL")
        self.assertFalse(any(event["type"] == "BUY" for event in payload["events"]))
        self.assertTrue(payload["context"]["ai_bias"]["long_block"])
        self.assertIn("trade_coherence", payload["context"])

    def test_bullish_ai_context_keeps_long_bias_active(self):
        payload = build_trend_breakout_payload(
            "PETR4",
            _make_rows("up"),
            timeframe="5m",
            ai_context={
                "market_regime": {"state": "bull_trend", "score": 78},
                "smart_money": {"state": "smart_money_active", "score": 81},
                "master_score": {"state": "high_conviction", "score": 89},
            },
        )

        self.assertIn(payload["signal"], {"BUY", "WATCH_BUY", "SELL", "COVER"})
        self.assertFalse(payload["context"]["ai_bias"]["long_block"])
        self.assertGreaterEqual(payload["context"]["ai_bias"]["master_score"], 89)

    def test_bdr_profile_is_stricter_than_b3(self):
        rows = _make_rows(
            "up",
            start=100.0,
            step=0.16,
            base_volume=1000.0,
            breakout_volume=1060.0,
            breakout_body=0.36,
        )

        b3_payload = build_trend_breakout_payload("PETR4", rows, timeframe="5m")
        bdr_payload = build_trend_breakout_payload("AAPL34.SA", rows, timeframe="5m")

        self.assertEqual(b3_payload["profile"], "b3_stock")
        self.assertEqual(bdr_payload["profile"], "bdr")
        self.assertIn(b3_payload["signal"], {"BUY", "WATCH_BUY", "SELL", "COVER", "NEUTRAL"})
        self.assertEqual(bdr_payload["signal"], "NEUTRAL")

    def test_crypto_profile_accepts_crypto_symbol(self):
        rows = _make_rows(
            "up",
            start=30000.0,
            step=18.0,
            base_volume=5000.0,
            breakout_volume=8200.0,
            breakout_body=110.0,
        )

        payload = build_trend_breakout_payload("BTC-USD", rows, timeframe="5m")

        self.assertEqual(payload["profile"], "crypto")
        self.assertIn(payload["signal"], {"BUY", "WATCH_BUY", "WATCH_SHORT", "SELL", "COVER", "NEUTRAL"})

    def test_chart_events_explain_trigger_invalidation_and_risk(self):
        payload = build_trend_breakout_payload(
            "PETR4",
            _make_rows("up"),
            timeframe="5m",
            ai_context={
                "market_regime": {"state": "bull_trend", "score": 78},
                "smart_money": {"state": "smart_money_active", "score": 81},
                "institutional_flow": {"state": "institutional_buying", "score": 82},
                "breakout_probability": {"state": "ready_to_break", "score": 80},
                "master_score": {"state": "high_conviction", "score": 89},
            },
        )
        buy_events = [event for event in payload["events"] if event["type"] == "BUY"]

        self.assertTrue(buy_events)
        self.assertTrue(buy_events[-1].get("trigger"))
        self.assertTrue(buy_events[-1].get("invalidation"))
        self.assertTrue(buy_events[-1].get("risk"))

    def test_chart_blocks_buy_when_ai_regime_is_downtrend(self):
        payload = build_trend_breakout_payload(
            "PETR4",
            _make_rows("up"),
            timeframe="5m",
            ai_context={
                "market_regime": {"state": "bear_trend", "score": 82},
                "smart_money": {"state": "retail_noise", "score": 22},
                "institutional_flow": {"state": "distribution_risk", "score": 18},
                "master_score": {"state": "weak_setup", "score": 32},
            },
        )

        self.assertFalse(any(event["type"] == "BUY" for event in payload["events"]))
        self.assertTrue(payload["context"]["ai_bias"]["long_block"])

    def test_intraday_position_is_closed_at_session_end(self):
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

        payload = build_trend_breakout_payload("ITUB4", rows, timeframe="5m")

        self.assertTrue(any(event["type"] == "BUY" for event in payload["events"]))
        self.assertEqual(payload["events"][-1]["type"], "SELL")
        self.assertEqual(payload["events"][-1]["reason"], "session_close")
        self.assertEqual(payload["signal"], "SELL")

    def test_b3_naive_local_session_end_closes_position(self):
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
        session_end = datetime(2026, 5, 18, 18, 0)
        start_time = session_end - timedelta(minutes=5 * (len(rows) - 1))
        for index, row in enumerate(rows):
            row["time"] = (start_time + timedelta(minutes=5 * index)).isoformat()

        payload = build_trend_breakout_payload("ITUB4", rows, timeframe="5m")

        self.assertEqual(payload["events"][-1]["type"], "SELL")
        self.assertEqual(payload["events"][-1]["reason"], "session_close")


if __name__ == "__main__":
    unittest.main()
