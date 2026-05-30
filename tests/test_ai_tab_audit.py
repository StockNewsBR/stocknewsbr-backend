import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.system.ai_tab_audit import _asset_class_for_ticker, get_ai_tab_audit_history, run_ai_tab_audit


class AiTabAuditTests(unittest.TestCase):
    def _snapshot_with_tool(self, *, score=82, state="strong_buying", confidence=90, ai_comment=None, trigger=None, invalidation=None):
        return {
            "signals": [
                {
                    "ticker": "PETR4",
                    "symbol": "PETR4",
                    "score": score,
                }
            ],
            "ai_tools": {
                "heat_map": [
                    {
                        "ticker": "PETR4",
                        "name": "Petrobras PN",
                        "score": score,
                        "signal": "BUY" if score >= 70 else "NEUTRAL",
                        "state": state,
                        "ai_comment": ai_comment or "Fluxo comprador acima da media e sustentado por volume.",
                        "trigger": trigger or "Manter acima da VWAP com volume relativo forte.",
                        "invalidation": invalidation or "Perda da VWAP com enfraquecimento do volume.",
                        "confidence": confidence,
                        "metrics": {"trend_strength": 72, "rel_volume": 1.8},
                    }
                ]
            },
        }

    def test_reports_degraded_when_snapshot_is_empty(self):
        with TemporaryDirectory() as tmp:
            with patch("app.system.ai_tab_audit.AI_TAB_AUDIT_DIR", Path(tmp)), patch("app.system.ai_tab_audit._history", []), patch("app.system.ai_tab_audit._last_report", {}):
                report = run_ai_tab_audit(snapshot={})

        self.assertEqual(report["overall_status"], "degraded")
        self.assertEqual(report["coverage"]["tools_present"], 0)
        self.assertIn("heat_map", report["tabs"])
        self.assertEqual(report["tabs"]["heat_map"]["status"], "empty")
        self.assertEqual(report["tabs"]["heat_map"]["approval_status"], "blocked")
        self.assertIn("benchmark", report)
        self.assertIn("qa_checklists", report)
        self.assertIn("comparisons", report)

    def test_flags_state_score_mismatch(self):
        snapshot = self._snapshot_with_tool(
            score=82,
            state="strong_selling",
            ai_comment="x",
            trigger="x",
            invalidation="x",
        )

        with TemporaryDirectory() as tmp:
            with patch("app.system.ai_tab_audit.AI_TAB_AUDIT_DIR", Path(tmp)), patch("app.system.ai_tab_audit._history", []), patch("app.system.ai_tab_audit._last_report", {}):
                report = run_ai_tab_audit(snapshot=snapshot)
        findings = report["tabs"]["heat_map"]["findings"]

        self.assertTrue(any(item["code"] == "state_score_mismatch" for item in findings))
        self.assertIn(report["tabs"]["heat_map"]["status"], {"warning", "degraded"})
        self.assertTrue(any(item["code"] == "weak_ai_comment" for item in findings))
        self.assertTrue(any(item["code"] == "weak_trigger" for item in findings))
        self.assertTrue(any(item["code"] == "weak_invalidation" for item in findings))
        self.assertIn(report["tabs"]["heat_map"]["approval_status"], {"watch", "blocked"})

    def test_builds_formal_quality_matrix_and_checklist(self):
        snapshot = self._snapshot_with_tool()
        with TemporaryDirectory() as tmp:
            with patch("app.system.ai_tab_audit.AI_TAB_AUDIT_DIR", Path(tmp)), patch("app.system.ai_tab_audit._history", []), patch("app.system.ai_tab_audit._last_report", {}):
                report = run_ai_tab_audit(snapshot=snapshot)

        tool = report["tabs"]["heat_map"]
        self.assertIn("benchmark_score", tool)
        self.assertIn("quality_matrix", tool)
        self.assertIn("qa_checklist", tool)
        self.assertEqual(sorted(tool["quality_matrix"].keys()), sorted(["coverage", "consistency", "confidence", "state_diversity", "explanation_quality", "product_quality"]))
        self.assertGreater(len(tool["qa_checklist"]), 0)
        self.assertIn("overall_approval", report["benchmark"])

    def test_compares_runs_and_records_history(self):
        first_snapshot = self._snapshot_with_tool(score=82, confidence=88)
        second_snapshot = self._snapshot_with_tool(score=60, state="mixed", confidence=52)

        with TemporaryDirectory() as tmp:
            with patch("app.system.ai_tab_audit.AI_TAB_AUDIT_DIR", Path(tmp)), patch("app.system.ai_tab_audit._history", []), patch("app.system.ai_tab_audit._last_report", {}):
                first = run_ai_tab_audit(snapshot=first_snapshot)
                second = run_ai_tab_audit(snapshot=second_snapshot)
                history = get_ai_tab_audit_history(limit=2)

        comparison = second["tabs"]["heat_map"]["comparison"]
        self.assertEqual(first["tabs"]["heat_map"]["comparison"]["status"], "first_run")
        self.assertIn(comparison["status"], {"stable", "watch", "drift"})
        self.assertIn("score_delta", comparison)
        self.assertGreaterEqual(len(history), 2)
        self.assertEqual(history[0]["generated_at"], second["generated_at"])

    def test_keeps_overall_status_warning_when_any_tab_has_warning(self):
        snapshot = self._snapshot_with_tool(
            ai_comment="x",
            trigger="x",
            invalidation="x",
        )
        with TemporaryDirectory() as tmp:
            with patch("app.system.ai_tab_audit.AI_TAB_AUDIT_DIR", Path(tmp)), patch("app.system.ai_tab_audit.AI_TAB_AUDIT_EXPORT_DIR", Path(tmp) / "exports"), patch("app.system.ai_tab_audit.AI_TAB_AUDIT_DATASET_DIR", Path(tmp) / "datasets"), patch("app.system.ai_tab_audit.AI_TAB_AUDIT_HISTORY_DIR", Path(tmp) / "history"), patch("app.system.ai_tab_audit._history", []), patch("app.system.ai_tab_audit._last_report", {}), patch("app.system.ai_tab_audit._build_benchmark_summary", return_value={"overall_approval": "approved", "approved_tools": 10, "watch_tools": 0, "blocked_tools": 0, "avg_benchmark_score": 90.0}):
                report = run_ai_tab_audit(snapshot=snapshot)

        self.assertEqual(report["benchmark"]["overall_approval"], "approved")
        self.assertEqual(report["tabs"]["heat_map"]["status"], "warning")
        self.assertEqual(report["overall_status"], "warning")
        self.assertFalse(report["release_decision"]["go_live"])

    def test_classifies_b3_suffix_sa_as_b3_instead_of_bdr(self):
        self.assertEqual(_asset_class_for_ticker("PETR4.SA"), "b3")
        self.assertEqual(_asset_class_for_ticker("VALE3.SA"), "b3")
        self.assertEqual(_asset_class_for_ticker("AAPL34.SA"), "bdr")

    def test_exports_dataset_when_ai_tools_are_derived_from_snapshot_signals(self):
        snapshot = {
            "signals": [
                {
                    "ticker": "PETR4",
                    "symbol": "PETR4",
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
                    "rel_volume": 1.6,
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
        with TemporaryDirectory() as tmp:
            export_dir = Path(tmp) / "exports"
            dataset_dir = Path(tmp) / "datasets"
            history_dir = Path(tmp) / "history"
            with patch("app.system.ai_tab_audit.AI_TAB_AUDIT_DIR", Path(tmp)), patch("app.system.ai_tab_audit.AI_TAB_AUDIT_EXPORT_DIR", export_dir), patch("app.system.ai_tab_audit.AI_TAB_AUDIT_DATASET_DIR", dataset_dir), patch("app.system.ai_tab_audit.AI_TAB_AUDIT_HISTORY_DIR", history_dir), patch("app.system.ai_tab_audit._history", []), patch("app.system.ai_tab_audit._last_report", {}):
                report = run_ai_tab_audit(snapshot=snapshot)

            dataset_path = Path(report["artifacts"]["dataset_csv"])
            self.assertTrue(dataset_path.exists())
            self.assertGreater(dataset_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
