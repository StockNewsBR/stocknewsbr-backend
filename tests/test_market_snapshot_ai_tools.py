import unittest

from app.engine.market_snapshot_engine import build_snapshot_payload


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
                "smart_money",
                "volatility_squeeze",
            ],
        )
        self.assertTrue(payload["ai_tools"]["institutional_flow"])
        self.assertTrue(payload["ai_tools"]["master_score"])
        self.assertTrue(payload["ai_tools"]["heat_map"])
        self.assertTrue(payload["ai_tools"]["breakout_probability"])
        self.assertTrue(payload["ai_tools"]["smart_money"])
        self.assertTrue(payload["ai_tools"]["liquidity_sweep"])
        self.assertTrue(payload["ai_tools"]["market_regime"])

        flow_row = payload["ai_tools"]["institutional_flow"][0]
        master_row = payload["ai_tools"]["master_score"][0]

        self.assertEqual(flow_row["ticker"], "PETR4")
        self.assertEqual(master_row["ticker"], "PETR4")
        self.assertEqual(master_row["tool"], "master_score")


if __name__ == "__main__":
    unittest.main()
