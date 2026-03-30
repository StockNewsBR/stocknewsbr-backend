import unittest

try:
    from app.services.chart_overlay_service import build_chart_overlays
    IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    IMPORT_ERROR = exc


@unittest.skipIf(IMPORT_ERROR is not None, f"runtime dependency unavailable: {IMPORT_ERROR}")
class ChartOverlayServiceTests(unittest.TestCase):
    def test_builds_markers_and_zones(self):
        ohlc = [
            {"time": "t1", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
            {"time": "t2", "open": 10, "high": 12, "low": 10, "close": 11, "volume": 110},
            {"time": "t3", "open": 11, "high": 13, "low": 10, "close": 12, "volume": 120},
        ]
        signals = [
            {
                "events": [
                    {"type": "BUY", "price": 11.2, "time": "t2"},
                    {"type": "SELL", "price": 12.4, "time": "t3"},
                ]
            }
        ]

        overlays = build_chart_overlays("PETR4", ohlc, signals)

        self.assertEqual(overlays["summary"]["ticker"], "PETR4")
        self.assertEqual(len(overlays["markers"]), 2)
        self.assertEqual(len(overlays["zones"]), 2)
        self.assertEqual(len(overlays["series"]), 3)


if __name__ == "__main__":
    unittest.main()
