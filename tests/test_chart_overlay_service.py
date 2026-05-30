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

    def test_trade_markers_use_operational_position_labels(self):
        ohlc = [
            {"time": f"t{index}", "open": 10 + index, "high": 11 + index, "low": 9 + index, "close": 10.5 + index, "volume": 100 + index}
            for index in range(1, 6)
        ]
        signals = [
            {
                "events": [
                    {"type": "BUY", "price": 11.2, "time": "t1", "trigger": "rompimento", "invalidation": "perdeu vwap", "risk": "baixo"},
                    {"type": "SELL", "price": 12.4, "time": "t2", "trigger": "saida", "invalidation": "recuperou", "risk": "medio"},
                    {"type": "SHORT", "price": 12.0, "time": "t3", "trigger": "perdeu suporte", "invalidation": "recuperou suporte", "risk": "alto"},
                    {"type": "COVER", "price": 10.8, "time": "t4", "trigger": "fechar short", "invalidation": "nova perda", "risk": "baixo"},
                ]
            }
        ]

        overlays = build_chart_overlays("PLTR", ohlc, signals)
        labels = [marker["label"] for marker in overlays["markers"]]

        self.assertEqual(labels, ["Buy Long", "Close Long", "Sell Short", "Close Short"])
        self.assertTrue(all(marker.get("trigger") for marker in overlays["markers"]))
        self.assertTrue(all(marker.get("invalidation") for marker in overlays["markers"]))
        self.assertTrue(all(marker.get("risk") for marker in overlays["markers"]))

    def test_does_not_pad_operational_chart_with_derived_watch_markers(self):
        ohlc = [
            {
                "time": f"t{index}",
                "open": 10 + index * 0.1,
                "high": 10.2 + index * 0.1,
                "low": 9.9 + index * 0.1,
                "close": 10.1 + index * 0.1,
                "volume": 100 + index,
            }
            for index in range(30)
        ]
        signals = [{"events": [{"type": "BUY", "price": 11.2, "time": "t12"}]}]

        overlays = build_chart_overlays("ITUB4", ohlc, signals, interval="1D")

        self.assertEqual(len(overlays["markers"]), 1)
        self.assertEqual(overlays["markers"][0]["type"], "BUY")

    def test_derived_watch_markers_are_capped_when_no_operational_trade_exists(self):
        ohlc = [
            {
                "time": f"t{index}",
                "open": 10 + index * 0.04,
                "high": 10.08 + index * 0.04,
                "low": 9.96 + index * 0.04,
                "close": 10.03 + index * 0.04,
                "volume": 100 + index,
            }
            for index in range(45)
        ]

        overlays = build_chart_overlays("ITUB4", ohlc, [], interval="1D")

        self.assertLessEqual(len(overlays["markers"]), 3)
        self.assertTrue(all(marker["type"] == "WATCH" for marker in overlays["markers"]))


if __name__ == "__main__":
    unittest.main()
