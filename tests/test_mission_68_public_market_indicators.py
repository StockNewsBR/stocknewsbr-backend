import math
import unittest
from unittest.mock import patch

import pandas as pd

from app.api import routes_public_market_live
from app.engine.indicators import vector_indicator_engine


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


class Mission68CanonicalRsiTests(unittest.TestCase):
    def test_canonical_latest_rsi_preserves_zero_and_requires_period_plus_one_candles(self):
        falling = pd.Series([float(value) for value in range(30, 15, -1)])

        self.assertEqual(vector_indicator_engine.compute_latest_rsi(falling), 0.0)
        self.assertIsNone(vector_indicator_engine.compute_latest_rsi(falling.iloc[:-1]))

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
                "timeframe": "1M",
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
            "as_of",
            "source",
            "candle_count",
            "required_count",
            "status",
            "reason",
        })
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
        rising = _ohlc_rows([float(v) for v in range(20, 40)])
        falling = _ohlc_rows([float(v) for v in range(40, 20, -1)])

        def fake_load(_ticker, interval):
            return rising if interval == "1D" else falling

        with patch.object(
            routes_public_market_live, "_load_chart_data_fast", side_effect=fake_load
        ), patch.object(
            routes_public_market_live, "build_chart_signal_payload", return_value={}
        ), patch.object(
            routes_public_market_live,
            "build_chart_overlays",
            return_value={"series": rising, "markers": [], "zones": [], "summary": {}},
        ):
            daily = routes_public_market_live.public_market_chart("PETR4", interval="1D")
            weekly = routes_public_market_live.public_market_chart("PETR4", interval="1W")

        self.assertEqual(daily["rsi_metadata"]["timeframe"], "1D")
        self.assertEqual(weekly["rsi_metadata"]["timeframe"], "1W")
        self.assertIsNotNone(daily["rsi"])
        self.assertIsNotNone(weekly["rsi"])
        self.assertNotEqual(daily["rsi"], weekly["rsi"])
        self.assertEqual(daily["rsi_metadata"]["source"], "canonical_indicator_engine")

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

    def test_empty_chart_payload_carries_pending_rsi_contract(self):
        with patch.object(routes_public_market_live, "_load_chart_data_fast", return_value=[]):
            payload = routes_public_market_live.public_market_chart("F", interval="3M")

        self.assertIsNone(payload["rsi"])
        self.assertEqual(payload["rsi_metadata"]["timeframe"], "3M")
        self.assertEqual(payload["rsi_metadata"]["status"], "PENDING")


if __name__ == "__main__":
    unittest.main()
