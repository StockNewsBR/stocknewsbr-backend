import unittest
from unittest.mock import patch

from app.engine import market_snapshot_engine
from app.engine.market_snapshot_engine import build_snapshot_payload
from app.cache.snapshot_cache import SnapshotCache
from app.ai.ai_specialists import OFFICIAL_AI_TOOL_KEYS


class MarketSnapshotAiToolsTests(unittest.TestCase):
    def test_snapshot_payload_includes_ai_tools(self):
        signals = [
            {
                "ticker": "PETR4",
                "name": "Petrobras PN",
                "score": 88.0,
                "price": 37.5,
                "prev_close": 36.9,
                "open": 37.0,
                "high": 38.1,
                "low": 36.8,
                "vwap": 37.2,
                "volume": 1_250_000,
                "avg_volume": 800_000,
                "rsi": 58.0,
                "adx": 24.0,
                "atr_pct": 1.9,
                "bb_width": 0.03,
                "kc_width": 0.05,
                "momentum": 1.2,
                "change_pct": 1.6,
                "rel_volume": 1.56,
                "market_regime_state": "bull_trend",
                "chart_regime_state": "trend_up",
                "above_vwap": True,
                "trend_strength": 68.0,
                "institutional_flow_score": 86.0,
                "institutional_flow_state": "institutional_buying",
                "smart_money_score": 84.0,
                "smart_money_state": "smart_money_active",
                "accumulation_score": 81.0,
                "accumulation_state": "accumulation",
                "breakout_probability_score": 79.0,
                "breakout_probability_state": "ready_to_break",
                "heat_map_score": 76.0,
                "heat_map_state": "strong_buying",
            }
        ]

        with patch.object(market_snapshot_engine, "get_market_pool", return_value={}):
            payload = build_snapshot_payload(signals)

        self.assertIn("ai_tools", payload)
        self.assertEqual(
            sorted(payload["ai_tools"].keys()),
            sorted(OFFICIAL_AI_TOOL_KEYS),
        )
        self.assertTrue(payload["ai_tools"]["flow"])
        self.assertTrue(payload["ai_tools"]["liquidity"])
        self.assertTrue(payload["ai_tools"]["trend"])
        self.assertTrue(payload["ai_tools"]["momentum"])
        self.assertTrue(payload["ai_tools"]["smart_money"])
        self.assertTrue(payload["ai_tools"]["risk"])
        self.assertTrue(payload["ai_tools"]["news"])
        self.assertTrue(payload["ai_tools"]["macro"])
        self.assertTrue(payload["ai_tools"]["regime"])
        self.assertNotIn("master_score", payload["ai_tools"])
        self.assertEqual(payload["ai_architecture"]["official_ai_count"], 9)
        self.assertEqual(payload["ai_architecture"]["trend_ia_decision"], "dedicated")
        self.assertFalse(payload["ai_architecture"]["master_score_exposed_as_ai"])
        self.assertIn("decision", payload)
        self.assertEqual(payload["decision"]["trade_action"], "NO_DECISION")
        self.assertFalse(payload["decision"]["decision_ready"])
        self.assertTrue(payload["decision"].get("blocked_reasons"))

        flow_row = payload["ai_tools"]["flow"][0]
        risk_row = payload["ai_tools"]["risk"][0]
        momentum_row = payload["ai_tools"]["momentum"][0]

        self.assertEqual(flow_row["ticker"], "PETR4")
        self.assertEqual(risk_row["ticker"], "PETR4")
        self.assertEqual(risk_row["tool"], "risk")
        self.assertIn("risk_score", risk_row)
        for row in (flow_row, risk_row, momentum_row):
            for field in ("detected_at", "trigger", "invalidation", "invalidacao", "metrics", "reason", "news_context"):
                self.assertIn(field, row)

    def test_snapshot_payload_keeps_one_canonical_market_row_for_cards_and_ai(self):
        market_time = "2026-04-06T10:00:00+00:00"
        signals = [
            {
                "ticker": "PETR4",
                "name": "Petrobras PN",
                "score": 88.0,
                "price": 37.5,
                "prev_close": 36.9,
                "open": 37.0,
                "high": 38.1,
                "low": 36.8,
                "vwap": 37.2,
                "volume": 1_250_000,
                "avg_volume": 800_000,
                "rel_volume": 1.5625,
                "rsi": 58.0,
                "macd": 0.12,
                "macd_signal": 0.08,
                "macd_histogram": 0.04,
                "adx": 24.0,
                "atr_pct": 1.9,
                "bb_width": 0.03,
                "kc_width": 0.05,
                "momentum": 1.2,
                "change_pct": 1.6,
                "data_quality": "cached",
                "market_data_updated_at": market_time,
                "last_bar_at": market_time,
            }
        ]

        payload = build_snapshot_payload(signals)

        signal_row = payload["signals"][0]
        symbol_row = payload["symbol_snapshots"]["PETR4"]
        risk_row = payload["ai_tools"]["risk"][0]

        for row in (signal_row, symbol_row, risk_row):
            self.assertEqual(row["ticker"], "PETR4")
            self.assertAlmostEqual(float(row["price"]), 37.5)
            self.assertEqual(int(row["volume"]), 1_250_000)
            self.assertAlmostEqual(float(row["rel_volume"]), 1.56, places=2)
            self.assertAlmostEqual(float(row["vwap"]), 37.2)
            self.assertAlmostEqual(float(row["rsi"]), 58.0)
            self.assertAlmostEqual(float(row["macd"]), 0.12)
            self.assertEqual(row["data_quality"], "cached")

        self.assertEqual(risk_row["market_data_updated_at"], market_time)
        self.assertEqual(risk_row["found_at"], market_time)
        self.assertEqual(risk_row["detected_at"], market_time)

    def test_generate_market_snapshot_reuses_last_good_snapshot_when_engine_is_empty(self):
        last_good = {
            "signals": [
                {
                    "ticker": "PETR4",
                    "name": "Petrobras PN",
                    "score": 88.0,
                    "price": 37.5,
                    "prev_close": 36.9,
                    "open": 37.0,
                    "high": 38.1,
                    "low": 36.8,
                    "vwap": 37.2,
                    "volume": 1_250_000,
                    "avg_volume": 800_000,
                    "rsi": 58.0,
                    "adx": 24.0,
                    "atr_pct": 1.9,
                    "bb_width": 0.03,
                    "kc_width": 0.05,
                    "momentum": 1.2,
                    "change_pct": 1.6,
                }
            ]
        }

        with patch.object(market_snapshot_engine, "get_all_signals", return_value=[]), patch.object(
            market_snapshot_engine, "run_engine", return_value=[]
        ), patch.object(
            market_snapshot_engine, "get_last_good_snapshot", return_value=last_good
        ), patch.object(
            market_snapshot_engine, "get_snapshot", return_value={"signals": []}
        ), patch.object(
            market_snapshot_engine, "store_signals"
        ), patch.object(
            market_snapshot_engine, "update_snapshot"
        ):
            payload = market_snapshot_engine.generate_market_snapshot()

        self.assertTrue(payload["signals"])
        self.assertTrue(payload["stale"])
        self.assertEqual(payload["source"], "snapshot_fallback")

    def test_generate_market_snapshot_empty_argument_uses_last_good_without_engine_rerun(self):
        last_good = {
            "signals": [
                {
                    "ticker": "PETR4",
                    "name": "Petrobras PN",
                    "score": 88.0,
                    "price": 37.5,
                    "prev_close": 36.9,
                    "open": 37.0,
                    "high": 38.1,
                    "low": 36.8,
                    "vwap": 37.2,
                    "volume": 1_250_000,
                    "avg_volume": 800_000,
                    "rsi": 58.0,
                    "adx": 24.0,
                    "atr_pct": 1.9,
                    "bb_width": 0.03,
                    "kc_width": 0.05,
                    "momentum": 1.2,
                    "change_pct": 1.6,
                }
            ]
        }

        with patch.object(market_snapshot_engine, "get_last_good_snapshot", return_value=last_good), patch.object(
            market_snapshot_engine,
            "run_engine",
        ) as rebuild, patch.object(
            market_snapshot_engine,
            "store_signals",
        ), patch.object(
            market_snapshot_engine,
            "update_snapshot",
        ):
            payload = market_snapshot_engine.generate_market_snapshot([], reuse_last_good_on_empty=True)

        self.assertFalse(rebuild.called)
        self.assertTrue(payload["signals"])
        self.assertTrue(payload["stale"])
        self.assertEqual(payload["source"], "snapshot_fallback")

    def test_last_good_snapshot_preserves_ai_metadata(self):
        cache = SnapshotCache()
        with patch.object(market_snapshot_engine, "get_market_pool", return_value={}):
            payload = build_snapshot_payload(
                [{"ticker": "PETR4", "score": 88.0, "signal": "buy", "state": "accumulation"}],
                source="signal_cache",
                stale=False,
            )

        cache.update(payload)
        last_good = cache.get_last_good()

        self.assertEqual(last_good.get("source"), "signal_cache")
        self.assertFalse(last_good.get("stale"))
        self.assertIn("ai_tools", last_good)
        self.assertTrue(last_good["ai_tools"].get("risk"))
        self.assertNotIn("master_score", last_good["ai_tools"])

    def test_snapshot_payload_without_ai_rows_keeps_no_decision(self):
        payload = build_snapshot_payload([], source="empty", stale=True)

        self.assertEqual(payload["decision"]["trade_action"], "NO_DECISION")
        self.assertFalse(payload["decision"]["decision_ready"])

    def test_snapshot_payload_freshness_status_for_stale_and_fresh_rows(self):
        old_updated = "2026-04-01T10:00:00+00:00"
        old_confirmed = "2026-04-01T10:00:00+00:00"
        stale_signals = [
            {
                "ticker": "PETR4",
                "score": 88.0,
                "signal": "buy",
                "state": "accumulation",
                "updated_at": old_updated,
                "last_confirmed_at": old_confirmed,
                "stale": True,
            }
        ]
        with patch.object(market_snapshot_engine, "get_market_pool", return_value={}):
            stale_payload = build_snapshot_payload(stale_signals, source="engine", stale=True)

        flow_stale = stale_payload["ai_tools"]["flow"][0]
        self.assertEqual(flow_stale["freshness_status"], "STALE")
        self.assertEqual(flow_stale.get("updated_at"), old_updated)
        self.assertEqual(flow_stale.get("last_confirmed_at"), old_confirmed)
        self.assertIn("snapshot_generated_at", flow_stale)

        fresh_signals = [
            {
                "ticker": "PETR4",
                "score": 88.0,
                "signal": "buy",
                "state": "accumulation",
            }
        ]
        with patch.object(market_snapshot_engine, "get_market_pool", return_value={}):
            fresh_payload = build_snapshot_payload(fresh_signals, source="engine", stale=False)

        flow_fresh = fresh_payload["ai_tools"]["flow"][0]
        self.assertEqual(flow_fresh["freshness_status"], "READY")
        self.assertEqual(flow_fresh["updated_at"], fresh_payload["generated_at"])
        self.assertEqual(flow_fresh["last_confirmed_at"], fresh_payload["generated_at"])
        self.assertEqual(flow_fresh["snapshot_generated_at"], fresh_payload["generated_at"])


if __name__ == "__main__":
    unittest.main()
