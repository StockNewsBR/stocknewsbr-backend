import math
import unittest
from unittest.mock import patch

import pandas as pd

from app.api import routes_public_market_live
from app.engine.indicators import vector_indicator_engine


def _minute_rows(closes):
    """Same shape as _ohlc_rows but spaced one minute apart, so the contract has a
    real intraday candle size to report instead of a daily one."""
    return [
        {
            "time": f"2026-07-17T14:{index:02d}:00+00:00",
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1_000,
        }
        for index, close in enumerate(closes)
    ]


def _ohlc_rows(closes, *, start_day=1):
    rows = []
    for index, close in enumerate(closes, start=start_day):
        rows.append(
            {
                "time": f"2026-07-{index:02d}T17:00:00+00:00",
                "open": close,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": 1_000,
            }
        )
    return rows


# Wilder's own published close series ("New Concepts in Technical Trading
# Systems"). Kept as a literal so the pinned RSI below is reproducible by hand.
_WILDER_REFERENCE_CLOSES = [
    44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
    45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64,
    46.21, 46.25, 45.71, 46.45, 45.78, 45.35, 44.03, 44.18, 44.22, 44.57,
]


class Mission68CanonicalRsiTests(unittest.TestCase):
    def test_rsi_uses_wilder_smoothing_not_cutler(self):
        """Pins the canonical RSI to Wilder (TradingView ta.rsi), not Cutler.

        Two anchors, because there are two distinct ways to silently regress:

        * 30 closes -> 45.4995. Cutler (rolling mean) would say 38.1426, so a
          revert to `rolling(period).mean()` fails here.
        * 15 closes -> 70.4641. At exactly period+1 candles Wilder and Cutler
          coincide by definition (the Wilder seed *is* the simple mean), so this
          anchor is blind to Cutler but catches a dropped seed: a bare
          `.ewm(alpha=1/period)` without the SMA seed says 50.6574.
        """
        thirty = pd.Series(_WILDER_REFERENCE_CLOSES)
        fifteen = pd.Series(_WILDER_REFERENCE_CLOSES[:15])

        self.assertAlmostEqual(vector_indicator_engine.compute_latest_rsi(thirty), 45.4995, places=4)
        self.assertAlmostEqual(vector_indicator_engine.compute_latest_rsi(fifteen), 70.4641, places=4)

    def test_canonical_latest_rsi_preserves_zero_and_requires_period_plus_one_candles(self):
        falling = pd.Series([float(value) for value in range(30, 15, -1)])

        self.assertEqual(vector_indicator_engine.compute_latest_rsi(falling), 0.0)
        self.assertIsNone(vector_indicator_engine.compute_latest_rsi(falling.iloc[:-1]))

    def test_uninterrupted_advance_is_fully_overbought(self):
        rising = pd.Series([float(value) for value in range(15, 30)])

        self.assertAlmostEqual(vector_indicator_engine.compute_latest_rsi(rising), 100.0, places=6)

    def test_flat_series_is_undefined_rsi_not_zero(self):
        flat = pd.Series([100.0] * 40)

        self.assertIsNone(vector_indicator_engine.compute_latest_rsi(flat))

    def test_latest_rsi_rejects_non_finite_and_extreme_periods(self):
        closes = pd.Series([float(value) for value in range(1, 20)])
        huge_integer = 10**1_000

        for invalid_period in (math.inf, -math.inf, huge_integer):
            with self.subTest(invalid_period=invalid_period):
                self.assertIsNone(vector_indicator_engine.compute_latest_rsi(closes, period=invalid_period))

    def test_latest_rsi_rejects_non_finite_and_overflowing_values(self):
        invalid_values = (math.nan, math.inf, -math.inf, 10**1_000)

        for invalid_value in invalid_values:
            with self.subTest(invalid_value=invalid_value):
                closes = [float(value) for value in range(1, 15)] + [invalid_value]
                self.assertIsNone(vector_indicator_engine.compute_latest_rsi(closes))

    def test_public_insight_uses_canonical_zero_with_symbol_timeframe_metadata(self):
        rows = _ohlc_rows([float(value) for value in range(30, 15, -1)])

        with patch.object(
            routes_public_market_live,
            "_load_chart_data_fast",
            return_value=rows,
        ), patch.object(
            routes_public_market_live,
            "build_chart_signal_payload",
            return_value={"rsi": 50.0, "score": 5.0, "summary": {"trend_bias": "baixa"}},
        ), patch.object(
            routes_public_market_live,
            "_snapshot_master_context",
            return_value={},
        ):
            payload = routes_public_market_live.public_market_insight("PETR4.SA", interval="1M")

        self.assertEqual(payload["rsi"], 0.0)
        self.assertEqual(
            payload["rsi_metadata"],
            {
                "symbol": "PETR4",
                # Range "1M" is served as DAILY candles, so the RSI is published as
                # daily -- the range label never masquerades as the candle size.
                "timeframe": "1d",
                "candle_interval": "1d",
                "period": 14,
                "as_of": rows[-1]["time"],
                "source": "canonical_indicator_engine",
                "candle_count": 15,
                "required_count": 15,
                "status": "AVAILABLE",
                "reason": None,
            },
        )

    def test_public_insight_does_not_replace_insufficient_rsi_with_fifty(self):
        rows = _ohlc_rows([10.0] * 14)

        with patch.object(
            routes_public_market_live,
            "_load_chart_data_fast",
            return_value=rows,
        ), patch.object(
            routes_public_market_live,
            "build_chart_signal_payload",
            return_value={"rsi": 50.0, "summary": {"trend_bias": "neutro"}},
        ), patch.object(
            routes_public_market_live,
            "_snapshot_master_context",
            return_value={},
        ):
            payload = routes_public_market_live.public_market_insight("VALE3", interval="1D")

        self.assertIsNone(payload["rsi"])
        self.assertEqual(payload["rsi_metadata"]["candle_count"], 14)
        self.assertEqual(payload["rsi_metadata"]["required_count"], 15)
        self.assertEqual(payload["rsi_metadata"]["status"], "INSUFFICIENT_DATA")
        self.assertEqual(payload["rsi_metadata"]["reason"], "insufficient_candles")

    def test_rsi_as_of_tracks_last_candle_used_by_the_calculation(self):
        rows = _ohlc_rows([float(value) for value in range(30, 15, -1)])
        invalid_tail_time = "2026-08-01T17:00:00+00:00"
        rows.append({"time": invalid_tail_time, "close": None})

        with patch.object(
            routes_public_market_live,
            "_load_chart_data_fast",
            return_value=rows,
        ), patch.object(
            routes_public_market_live,
            "build_chart_signal_payload",
            return_value={},
        ), patch.object(
            routes_public_market_live,
            "_snapshot_master_context",
            return_value={},
        ):
            payload = routes_public_market_live.public_market_insight("ITUB4", interval="1D")

        self.assertEqual(payload["rsi_metadata"]["as_of"], rows[-2]["time"])
        self.assertNotEqual(payload["rsi_metadata"]["as_of"], invalid_tail_time)

    def test_empty_public_insight_keeps_complete_pending_rsi_contract(self):
        with patch.object(routes_public_market_live, "_load_chart_data_fast", return_value=[]), patch.object(
            routes_public_market_live,
            "_snapshot_master_context",
            return_value={},
        ):
            payload = routes_public_market_live.public_market_insight("F", interval="3M")

        self.assertIsNone(payload["rsi"])
        self.assertEqual(set(payload["rsi_metadata"]), {
            "symbol",
            "timeframe",
            "candle_interval",
            "period",
            "as_of",
            "source",
            "candle_count",
            "required_count",
            "status",
            "reason",
        })
        self.assertEqual(payload["rsi_metadata"]["period"], 14)
        self.assertEqual(payload["rsi_metadata"]["symbol"], "F")
        self.assertEqual(payload["rsi_metadata"]["timeframe"], "3M")
        self.assertEqual(payload["rsi_metadata"]["status"], "PENDING")
        self.assertEqual(payload["rsi_metadata"]["reason"], "empty_chart")

    def test_quote_fallback_candles_never_become_rsi(self):
        rows = _ohlc_rows([float(value) for value in range(30, 15, -1)])
        for row in rows:
            row["source"] = "quote_cache_fallback"

        with patch.object(
            routes_public_market_live,
            "_load_chart_data_fast",
            return_value=rows,
        ), patch.object(
            routes_public_market_live,
            "_snapshot_master_context",
            return_value={},
        ):
            payload = routes_public_market_live.public_market_insight("PETR4", interval="1D")

        self.assertIsNone(payload["rsi"])
        self.assertEqual(payload["rsi_metadata"]["status"], "INSUFFICIENT_DATA")
        self.assertEqual(payload["rsi_metadata"]["reason"], "non_canonical_chart_source")


class Mission68CanonicalChartLevelTests(unittest.TestCase):
    def test_english_support_label_without_explicit_kind_is_preserved(self):
        rows = _ohlc_rows([10.0, 10.2, 10.4])

        zones = routes_public_market_live.normalize_public_chart_zones(
            [{"label": "Support", "price": 9.5}],
            symbol="AAPL",
            timeframe="1D",
            rows=rows,
        )

        self.assertEqual(zones[0]["kind"], "support")

    def test_support_and_resistance_share_the_chart_calculation_as_of(self):
        rows = _ohlc_rows([10.0, 10.2, 10.4])

        zones = routes_public_market_live.normalize_public_chart_zones(
            [
                {"label": "Support", "price": 9.5},
                {"label": "Resistance", "price": 10.8},
            ],
            symbol="AAPL",
            timeframe="1D",
            rows=rows,
        )

        self.assertEqual({zone["as_of"] for zone in zones}, {rows[-1]["time"]})
        self.assertEqual({zone["kind"] for zone in zones}, {"support", "resistance"})

    def test_chart_keeps_only_existing_level_and_adds_level_context(self):
        rows = _ohlc_rows([10.0, 10.2, 10.4])
        support = {"label": "suporte", "price": 9.5}

        with patch.object(
            routes_public_market_live,
            "_load_chart_data_fast",
            return_value=rows,
        ), patch.object(
            routes_public_market_live,
            "build_chart_signal_payload",
            return_value={},
        ), patch.object(
            routes_public_market_live,
            "build_chart_overlays",
            return_value={"series": rows, "markers": [], "zones": [support], "summary": {}},
        ):
            payload = routes_public_market_live.public_market_chart("PETR4", interval="1W")

        self.assertEqual(len(payload["zones"]), 1)
        self.assertEqual(payload["zones"][0]["kind"], "support")
        self.assertEqual(payload["zones"][0]["symbol"], "PETR4")
        self.assertEqual(payload["zones"][0]["timeframe"], "1W")
        self.assertEqual(payload["zones"][0]["as_of"], rows[-1]["time"])
        self.assertNotIn("resistance", {zone.get("kind") for zone in payload["zones"]})

    def test_chart_does_not_repeat_same_price_as_support_and_resistance(self):
        rows = _ohlc_rows([10.0, 10.0, 10.0])
        duplicate_levels = [
            {"label": "resistencia", "price": 10.0},
            {"label": "suporte", "price": 10.0},
            {"label": "suporte", "price": None},
        ]

        with patch.object(
            routes_public_market_live,
            "_load_chart_data_fast",
            return_value=rows,
        ), patch.object(
            routes_public_market_live,
            "build_chart_signal_payload",
            return_value={},
        ), patch.object(
            routes_public_market_live,
            "build_chart_overlays",
            return_value={"series": rows, "markers": [], "zones": duplicate_levels, "summary": {}},
        ):
            payload = routes_public_market_live.public_market_chart("VALE3", interval="1D")

        self.assertEqual([zone["price"] for zone in payload["zones"]], [10.0])

    def test_chart_does_not_publish_levels_from_quote_fallback_candles(self):
        rows = _ohlc_rows([10.0, 10.2, 10.4])
        for row in rows:
            row["source"] = "quote_cache_fallback"

        with patch.object(
            routes_public_market_live,
            "_load_chart_data_fast",
            return_value=rows,
        ), patch.object(
            routes_public_market_live,
            "build_chart_overlays",
            return_value={
                "series": rows,
                "markers": [],
                "zones": [
                    {"label": "resistencia", "price": 10.9},
                    {"label": "suporte", "price": 9.5},
                ],
                "summary": {},
            },
        ):
            payload = routes_public_market_live.public_market_chart("PETR4", interval="1D")

        self.assertEqual(payload["zones"], [])


class Mission68ChartTimeframeRsiTests(unittest.TestCase):
    def test_chart_exposes_per_timeframe_rsi_independent_from_daily(self):
        minute_rows = _minute_rows([float(v) for v in range(40, 20, -1)])
        daily_rows = _ohlc_rows([float(v) for v in range(20, 40)])

        def fake_load(_ticker, interval):
            return minute_rows if interval == "@1M" else daily_rows

        with patch.object(
            routes_public_market_live, "_load_chart_data_fast", side_effect=fake_load
        ), patch.object(
            routes_public_market_live, "build_chart_signal_payload", return_value={}
        ), patch.object(
            routes_public_market_live,
            "build_chart_overlays",
            return_value={"series": daily_rows, "markers": [], "zones": [], "summary": {}},
        ):
            minute = routes_public_market_live.public_market_chart("PETR4", candles="1m")
            daily = routes_public_market_live.public_market_chart("PETR4", candles="1d")

        # The requested candle size is what the RSI is computed on AND reported as.
        self.assertEqual(minute["rsi_metadata"]["timeframe"], "1m")
        self.assertEqual(daily["rsi_metadata"]["timeframe"], "1d")
        self.assertIsNotNone(minute["rsi"])
        self.assertIsNotNone(daily["rsi"])
        # Guards against the interval being ignored: one series falls, the other rises.
        self.assertNotEqual(minute["rsi"], daily["rsi"])
        self.assertEqual(daily["rsi_metadata"]["source"], "canonical_indicator_engine")

    def test_requested_candle_interval_is_not_confused_with_the_range_label(self):
        # "1M" the range is a month of daily candles; "1m" the candle size is a minute.
        self.assertEqual(routes_public_market_live._normalize_candle_interval("1m"), "@1M")
        self.assertEqual(routes_public_market_live._normalize_candle_interval("1h"), "@1H")
        self.assertIsNone(routes_public_market_live._normalize_candle_interval("3M"))
        self.assertIsNone(routes_public_market_live._normalize_candle_interval(None))
        # A range request keeps using the range map, never the candle namespace.
        self.assertEqual(routes_public_market_live._normalize_chart_interval("3M", None), "3M")

    def test_candle_request_falls_back_to_the_range_that_already_serves_it(self):
        # Routes are cache-only, so a candle size with no warmed series of its own
        # must reuse the warmed range that produces exactly those candles.
        asked = []

        def fake_rows(_aliases, interval, scope="public_market_live"):
            asked.append(interval)
            return _ohlc_rows([float(v) for v in range(20, 40)]) if interval == "3M" else []

        with patch.object(routes_public_market_live, "load_public_chart_rows", side_effect=fake_rows):
            rows = routes_public_market_live._load_chart_data_fast("AAPL", "@1D")

        self.assertEqual(asked, ["@1D", "3M"])
        self.assertTrue(rows)
        # One minute has no warmed range: stay empty rather than serve other candles.
        with patch.object(routes_public_market_live, "load_public_chart_rows", return_value=[]) as loader:
            self.assertEqual(routes_public_market_live._load_chart_data_fast("AAPL", "@1M"), [])
        self.assertEqual(loader.call_count, 1)

    def test_insufficient_candles_for_requested_interval_is_null_never_zero(self):
        rows = _minute_rows([10.0] * 12)

        with patch.object(
            routes_public_market_live, "_load_chart_data_fast", return_value=rows
        ), patch.object(
            routes_public_market_live, "build_chart_signal_payload", return_value={}
        ), patch.object(
            routes_public_market_live,
            "build_chart_overlays",
            return_value={"series": rows, "markers": [], "zones": [], "summary": {}},
        ):
            payload = routes_public_market_live.public_market_chart("AAPL", candles="1m")

        self.assertIsNone(payload["rsi"])
        self.assertNotEqual(payload["rsi"], 0)
        self.assertEqual(payload["rsi_metadata"]["timeframe"], "1m")
        self.assertEqual(payload["rsi_metadata"]["status"], "INSUFFICIENT_DATA")
        self.assertEqual(payload["rsi_metadata"]["reason"], "insufficient_candles")

    def test_chart_rsi_is_null_when_candles_insufficient(self):
        rows = _ohlc_rows([10.0] * 14)
        with patch.object(
            routes_public_market_live, "_load_chart_data_fast", return_value=rows
        ), patch.object(
            routes_public_market_live, "build_chart_signal_payload", return_value={}
        ), patch.object(
            routes_public_market_live,
            "build_chart_overlays",
            return_value={"series": rows, "markers": [], "zones": [], "summary": {}},
        ):
            payload = routes_public_market_live.public_market_chart("VALE3", interval="1D")

        self.assertIsNone(payload["rsi"])
        self.assertEqual(payload["rsi_metadata"]["status"], "INSUFFICIENT_DATA")
        self.assertEqual(payload["rsi_metadata"]["candle_count"], 14)

    def test_rsi_metadata_reports_real_candle_spacing_not_the_range_label(self):
        # "1D" is a *range* (one day of 5m candles), not a daily candle size.
        intraday = [
            {"time": f"2026-07-17 08:{minute:02d}:00+00:00", "close": 100.0 + minute}
            for minute in range(0, 60, 5)
        ]

        contract = routes_public_market_live.build_public_rsi_contract("AAPL", "1D", intraday)

        # The published timeframe is the real spacing of the candles the RSI used,
        # so a 5m read can never reach the UI wearing a "1D" label.
        self.assertEqual(contract["rsi_metadata"]["timeframe"], "5m")
        self.assertEqual(contract["rsi_metadata"]["candle_interval"], "5m")

    def test_empty_chart_payload_carries_pending_rsi_contract(self):
        with patch.object(routes_public_market_live, "_load_chart_data_fast", return_value=[]):
            payload = routes_public_market_live.public_market_chart("F", interval="3M")

        self.assertIsNone(payload["rsi"])
        self.assertEqual(payload["rsi_metadata"]["timeframe"], "3M")
        self.assertEqual(payload["rsi_metadata"]["status"], "PENDING")


if __name__ == "__main__":
    unittest.main()
