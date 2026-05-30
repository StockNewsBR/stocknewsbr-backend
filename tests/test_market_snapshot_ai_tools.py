import unittest
from unittest.mock import patch

from app.engine import market_snapshot_engine
from app.engine.market_snapshot_engine import build_snapshot_payload
from app.cache.snapshot_cache import SnapshotCache


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
            }
        ]

        payload = build_snapshot_payload(signals)

        self.assertIn("ai_tools", payload)
        self.assertEqual(
            sorted(payload["ai_tools"].keys()),
            [
                "accumulation",
                "breakout_probability",
                "heat_map",
                "institutional_flow",
                "liquidity_map",
                "liquidity_sweep",
                "market_regime",
                "master_score",
                "radar",
                "smart_money",
                "volatility_squeeze",
            ],
        )
        self.assertTrue(payload["ai_tools"]["institutional_flow"])
        self.assertTrue(payload["ai_tools"]["master_score"])
        self.assertTrue(payload["ai_tools"]["heat_map"])
        self.assertTrue(payload["ai_tools"]["radar"])
        self.assertTrue(payload["ai_tools"]["breakout_probability"])
        self.assertTrue(payload["ai_tools"]["smart_money"])
        self.assertTrue(payload["ai_tools"]["liquidity_sweep"])
        self.assertTrue(payload["ai_tools"]["market_regime"])
        self.assertIn("decision", payload)
        self.assertIn(payload["decision"]["trade_action"], {"BUY", "SELL", "SHORT", "COVER"})

        flow_row = payload["ai_tools"]["institutional_flow"][0]
        master_row = payload["ai_tools"]["master_score"][0]
        radar_row = payload["ai_tools"]["radar"][0]

        self.assertEqual(flow_row["ticker"], "PETR4")
        self.assertEqual(master_row["ticker"], "PETR4")
        self.assertEqual(master_row["tool"], "master_score")
        self.assertIn(master_row["signal"], {"BUY", "SELL", "SHORT", "COVER"})
        for row in (flow_row, master_row, radar_row):
            for field in ("detected_at", "trigger", "invalidation", "invalidacao", "metrics", "reason", "news_context"):
                self.assertIn(field, row)

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
        self.assertTrue(last_good["ai_tools"].get("master_score"))

    def test_snapshot_payload_without_ai_rows_keeps_no_decision(self):
        payload = build_snapshot_payload([], source="empty", stale=True)

        self.assertEqual(payload["decision"]["trade_action"], "NO_DECISION")
        self.assertFalse(payload["decision"]["decision_ready"])


if __name__ == "__main__":
    unittest.main()
