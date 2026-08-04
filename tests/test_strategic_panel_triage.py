import unittest
from app.ai.strategic_panel import apply_strategic_panels_by_ticker


class StrategicPanelTriageTests(unittest.TestCase):
    def test_strategic_panel_behavior(self):
        # master_score_rows tem PETR4. normalized tem PETR4 e PETR4.SA.
        strategic_panels = [
            {
                "ticker": "PETR4",
                "strategic_panel_summary": "PETR4 Panel",
                "recommended_action": "COMPRAR",
            }
        ]

        normalized = [
            {"ticker": "PETR4", "symbol": "PETR4"},
            {"ticker": "PETR4.SA", "symbol": "PETR4.SA"},
            {"ticker": "UNSUPPORTED", "symbol": "UNSUPPORTED"},
        ]

        result = apply_strategic_panels_by_ticker(normalized, strategic_panels)

        petr4 = next(r for r in result if r["ticker"] == "PETR4")
        petr4_sa = next(r for r in result if r["ticker"] == "PETR4.SA")
        unsupported = next(r for r in result if r["ticker"] == "UNSUPPORTED")

        self.assertIn("strategic_panel", petr4, "PETR4 received its panel")

        # 4. PETR4 e PETR4.SA recebem o painel corretamente via fallback/canônico.
        self.assertIn(
            "strategic_panel",
            petr4_sa,
            "PETR4.SA received cross panel from PETR4 because it canonicalizes to PETR4",
        )

        # 5. ticker não suportado não recebe painel falso
        self.assertNotIn(
            "strategic_panel", unsupported, "UNSUPPORTED received cross panel"
        )


if __name__ == "__main__":
    unittest.main()
