import unittest

from app.ai.ai_common import build_payload


class AiCommonPayloadTests(unittest.TestCase):
    def test_payload_prefers_market_timestamp_over_worker_cycle_time(self):
        payload = build_payload(
            {
                "ticker": "F",
                "detected_at": "2026-05-18T15:23:00+00:00",
                "market_data_updated_at": "2026-05-18T08:05:00-04:00",
                "updated_at": "2026-05-18T15:23:00+00:00",
            },
            "heat_map",
            7.2,
            "premarket_strength",
            "Forca relativa no pre-market.",
            "Confirmar rompimento com volume.",
            "Invalidar se perder VWAP.",
        )

        self.assertEqual(payload["detected_at"], "2026-05-18T12:05:00+00:00")
        self.assertEqual(payload["updated_at"], "2026-05-18T12:05:00+00:00")


if __name__ == "__main__":
    unittest.main()
