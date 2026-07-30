import unittest

import numpy as np
import pandas as pd

from app.engine.core.engine_v36 import run_engine


def _engine_frame(final_volume=5_000_000):
    periods = 140
    closes = [10.0 + index * 0.01 for index in range(periods)]
    closes[-1] = closes[-2] + 1.0
    volumes = [100_000 + index * 500 for index in range(periods)]
    volumes[-1] = final_volume
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [value * 1.01 for value in closes],
            "Low": [value * 0.99 for value in closes],
            "Close": closes,
            "Volume": volumes,
        },
        index=pd.date_range("2026-05-14 10:00", periods=periods, freq="5min", tz="UTC"),
    )


class EngineV36EnrichmentTests(unittest.TestCase):
    def test_run_engine_enriches_rows_with_market_fields(self):
        result = run_engine({"PETR4.SA": _engine_frame()})

        self.assertTrue(result)
        row = result[0]

        self.assertEqual(row["ticker"], "PETR4.SA")
        self.assertEqual(row["symbol"], "PETR4.SA")
        self.assertGreater(row["price"], 0)
        self.assertGreater(row["volume"], 0)
        self.assertGreater(row["avg_volume"], 0)
        self.assertGreater(row["rel_volume"], 1.0)
        self.assertIn("change_pct", row)
        self.assertIn("vwap", row)
        self.assertEqual(row["data_quality"], "priced")
        self.assertEqual(row["price_source"], "engine_v36_matrix")
        self.assertEqual(row["volume_source"], "engine_v36_matrix")

    def test_run_engine_marks_zero_volume_as_score_only(self):
        result = run_engine({"PETR4.SA": _engine_frame(final_volume=0)})

        self.assertTrue(result)
        row = result[0]

        self.assertEqual(row["volume"], 0)
        self.assertEqual(row["data_quality"], "score_only")

    def test_run_engine_rejects_non_finite_values(self):
        """NaN/Inf in price/volume must be sanitized, not produce NaN scores or drop symbols silently."""
        periods = 140
        closes = [10.0 + index * 0.01 for index in range(periods)]
        closes[-1] = closes[-2] + 1.0
        # Inject NaN and Inf in the critical 21-period window
        closes[120] = np.nan
        closes[125] = np.inf
        closes[130] = -np.inf
        volumes = [100_000 + index * 500 for index in range(periods)]
        volumes[-1] = 5_000_000

        df = pd.DataFrame(
            {
                "Open": closes,
                "High": [value * 1.01 if np.isfinite(value) else 10.0 for value in closes],
                "Low": [value * 0.99 if np.isfinite(value) else 10.0 for value in closes],
                "Close": closes,
                "Volume": volumes,
            },
            index=pd.date_range("2026-05-14 10:00", periods=periods, freq="5min", tz="UTC"),
        )

        result = run_engine({"TEST1.SA": df})

        self.assertTrue(result, "Symbol should not be dropped silently")
        row = result[0]

        self.assertEqual(row["ticker"], "TEST1.SA")
        self.assertTrue(np.isfinite(row["score"]), "Score must be finite")
        self.assertNotEqual(row["score"], 0.0, "Score should not be zero after sanitization")
        self.assertEqual(row["data_quality"], "priced")


if __name__ == "__main__":
    unittest.main()
