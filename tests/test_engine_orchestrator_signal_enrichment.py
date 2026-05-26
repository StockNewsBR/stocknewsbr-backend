import unittest
from unittest.mock import patch

import pandas as pd

from app.engine import engine_orchestrator


def _market_frame():
    return pd.DataFrame(
        {
            "Open": [10.0, 10.4, 10.7],
            "High": [10.5, 10.9, 11.3],
            "Low": [9.8, 10.2, 10.6],
            "Close": [10.2, 10.8, 11.0],
            "Volume": [100_000, 120_000, 180_000],
        },
        index=pd.date_range("2026-05-14 10:00", periods=3, freq="5min", tz="UTC"),
    )


class EngineOrchestratorSignalEnrichmentTests(unittest.TestCase):
    def test_enrich_ranked_with_real_price_and_volume_from_market_pool(self):
        enriched = engine_orchestrator._enrich_ranked_with_market_data(
            [{"ticker": "PETR4.SA", "symbol": "PETR4.SA", "score": 82.0}],
            {"PETR4.SA": _market_frame()},
        )

        row = enriched[0]

        self.assertEqual(row["ticker"], "PETR4.SA")
        self.assertEqual(row["price"], 11.0)
        self.assertEqual(row["close"], 11.0)
        self.assertEqual(row["prev_close"], 10.8)
        self.assertEqual(row["volume"], 180_000)
        self.assertEqual(row["avg_volume"], 133_333)
        self.assertEqual(row["data_quality"], "priced")
        self.assertEqual(row["price_source"], "warm_market_pool")
        self.assertEqual(row["volume_source"], "warm_market_pool")
        self.assertGreater(row["rel_volume"], 1.0)
        self.assertIn("market_data_updated_at", row)

    def test_enrich_ranked_keeps_score_only_when_market_data_is_missing(self):
        enriched = engine_orchestrator._enrich_ranked_with_market_data(
            [{"ticker": "VALE3.SA", "symbol": "VALE3.SA", "score": 80.0}],
            {"PETR4.SA": _market_frame()},
        )

        row = enriched[0]

        self.assertEqual(row["ticker"], "VALE3.SA")
        self.assertEqual(row["data_quality"], "score_only")
        self.assertNotIn("price", row)
        self.assertNotIn("volume", row)

    def test_run_engine_updates_signal_cache_with_enriched_rows(self):
        pool = {"PETR4.SA": _market_frame()}
        ranked = [{"ticker": "PETR4.SA", "symbol": "PETR4.SA", "score": 82.0}]

        with patch.object(engine_orchestrator, "get_market_pool", return_value=pool), patch.object(
            engine_orchestrator,
            "run_engine_v36",
            return_value=ranked,
        ), patch.object(
            engine_orchestrator,
            "detect_price_events",
            return_value=[],
        ), patch.object(
            engine_orchestrator,
            "update_signals",
        ) as update_signals, patch.object(
            engine_orchestrator,
            "record_worker_stage_duration",
        ), patch.object(
            engine_orchestrator,
            "record_cycle",
        ):
            result = engine_orchestrator.run_engine()

        cached_row = update_signals.call_args.args[0][0]

        self.assertEqual(result[0]["price"], 11.0)
        self.assertEqual(result[0]["volume"], 180_000)
        self.assertEqual(result[0]["data_quality"], "priced")
        self.assertEqual(cached_row["price"], 11.0)
        self.assertEqual(cached_row["volume"], 180_000)
        self.assertEqual(cached_row["data_quality"], "priced")


if __name__ == "__main__":
    unittest.main()
