import unittest

from app.ai.ai_radar import run_radar


class AiRadarTests(unittest.TestCase):
    def test_radar_uses_acceleration_and_volume_metrics(self):
        rows = [
            {
                "ticker": "F",
                "price": 12.2,
                "prev_close": 12.0,
                "volume": 2_400_000,
                "avg_volume": 1_000_000,
                "rel_volume": 2.4,
                "momentum": 1.3,
                "change_pct": 1.7,
                "trend_strength": 61,
                "atr_pct": 1.8,
            },
            {
                "ticker": "AAPL",
                "price": 287.0,
                "prev_close": 287.0,
                "volume": 200_000,
                "avg_volume": 1_000_000,
                "rel_volume": 0.2,
                "momentum": 0.0,
                "change_pct": 0.0,
                "trend_strength": 40,
                "atr_pct": 0.7,
            },
        ]

        payload = run_radar(rows, limit=2)

        self.assertEqual(payload[0]["ticker"], "F")
        self.assertEqual(payload[0]["tool"], "radar")
        self.assertGreater(payload[0]["score"], payload[1]["score"])
        self.assertIn("velocity", payload[0]["metrics"])
        self.assertIn(payload[0]["state"], {"momentum_ignition", "fast_move", "early_radar"})


if __name__ == "__main__":
    unittest.main()
