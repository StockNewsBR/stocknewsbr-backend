import json
import os
import subprocess
import sys
import tempfile
import typing
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pandas as pd

from app.ai.final_decision import enrich_final_decision_rows
from app.ai.trade_decision import summarize_trade_decision
from app.engine.core.signal_fusion_engine import run_signal_fusion
from app.engine.scanners.momentum_scanner import detect_acceleration
from app.engine.scanners.smart_money_scanner import scan_smart_money
from app.services import ranking
from app.services.score_display import attach_master_score_display_contract, normalize_master_score_display, resolve_master_score_display_value
from app.services.snapshot_contract import DECISION_BLOCKED, build_decision_envelope, has_blocking_reasons, is_actionable_snapshot_row
from app.system import push_dispatcher
from app.system.performance_intelligence import score_bucket
from app.telegram.telegram_alert_engine import _alert_priority_score_value, _event_payload
from app.telegram.telegram_alert_formatter import format_signal_alert
from app.web import routes_radar as web_radar


REPO_ROOT = Path(__file__).resolve().parents[1]


def _bullish_decision_row(**overrides):
    row = {
        "ticker": "PETR4",
        "score": 88,
        "price": 37.5,
        "volume": 1_200_000,
        "rel_volume": 1.6,
        "market_regime_state": "bull_trend",
        "chart_regime_state": "trend_up",
        "above_vwap": True,
        "trend_strength": 68,
        "trade_confidence": 72,
        "institutional_flow_score": 86,
        "institutional_flow_state": "institutional_buying",
        "smart_money_score": 84,
        "smart_money_state": "smart_money_active",
        "accumulation_score": 81,
        "accumulation_state": "accumulation",
        "breakout_probability_score": 79,
        "breakout_probability_state": "ready_to_break",
        "heat_map_score": 76,
        "heat_map_state": "strong_buying",
    }
    row.update(overrides)
    return row


def _bearish_decision_row(**overrides):
    row = {
        "ticker": "VALE3",
        "score": 22,
        "price": 62.1,
        "volume": 1_100_000,
        "rel_volume": 1.6,
        "market_regime_state": "bear_trend",
        "chart_regime_state": "trend_down",
        "above_vwap": False,
        "trend_strength": 62,
        "trade_confidence": 72,
        "institutional_flow_score": 18,
        "institutional_flow_state": "distribution_risk",
        "smart_money_score": 22,
        "smart_money_state": "retail_noise",
        "accumulation_score": 14,
        "accumulation_state": "distribution_or_weak",
        "breakout_probability_score": 20,
        "breakout_probability_state": "not_ready",
        "heat_map_score": 30,
        "heat_map_state": "strong_selling",
    }
    row.update(overrides)
    return row


def _final_decision_row(**overrides):
    row = {
        "ticker": "PETR4",
        "symbol": "PETR4",
        "signal": "BUY",
        "trade_action": "BUY",
        "decision_ready": True,
        "operational_status": "READY",
        "master_confidence": "Media",
        "priority_score": 50.0,
        "conviction_score": 50.0,
        "ranking_opportunity_score": 50.0,
        "radar_prioritization_score": 50.0,
        "historical_confidence_score": 50.0,
        "operational_score": 50.0,
        "price": 37.5,
        "volume": 1_000_000,
        "rel_volume": 1.2,
        "data_quality": "cached",
    }
    row.update(overrides)
    return row


class Mission31CCriticalCleanupTests(unittest.TestCase):
    def test_signal_fusion_exception_returns_empty_list(self):
        with self.assertLogs("stocknewsbr.engine.signal_fusion", level="ERROR") as captured:
            with patch(
                "app.engine.core.signal_fusion_engine.scan_momentum",
                side_effect=RuntimeError("mission-31c simulated failure"),
            ):
                result = run_signal_fusion([{"symbol": "PETR4"}])

        self.assertIsInstance(result, list)
        self.assertEqual(result, [])
        self.assertTrue(any("signal fusion" in line.lower() for line in captured.output))

    def test_momentum_acceleration_exception_returns_empty_list(self):
        with self.assertLogs("stocknewsbr.scanner.momentum", level="ERROR") as captured:
            with patch(
                "app.engine.scanners.momentum_scanner._safe_float",
                side_effect=ValueError("mission-31c simulated failure"),
            ):
                result = detect_acceleration([{"symbol": "PETR4", "change_pct": "1.0"}])

        self.assertIsInstance(result, list)
        self.assertEqual(result, [])
        self.assertTrue(any("momentum acceleration" in line.lower() for line in captured.output))

    def test_smart_money_exception_returns_empty_list(self):
        with self.assertLogs("stocknewsbr.scanner.smart_money", level="ERROR") as captured:
            with patch(
                "app.engine.scanners.smart_money_scanner._safe_float",
                side_effect=ValueError("mission-31c simulated failure"),
            ):
                result = scan_smart_money([{"symbol": "PETR4", "volume": 10, "avg_volume": 5}])

        self.assertIsInstance(result, list)
        self.assertEqual(result, [])
        self.assertTrue(any("smart money" in line.lower() for line in captured.output))

    def test_ranking_pandas_contract_imports_and_scores(self):
        hints = typing.get_type_hints(ranking.calculate_score)
        self.assertIs(hints["df"], pd.DataFrame)
        self.assertIsNone(ranking._numeric_score_or_none(pd.NA))

        frame = pd.DataFrame(
            {
                "Close": [10, 11, 12, 13, 14, 13, 12, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24],
                "Volume": [100] * 21,
            }
        )
        score = ranking.calculate_score("TST", frame)
        self.assertIsInstance(score, dict)
        self.assertEqual(score["symbol"], "TST")

    def test_snapshot_ranking_score_matches_master_display_when_raw_exists(self):
        row = _bullish_decision_row(
            canonical_symbol="PETR4",
            master_score_raw=87.0,
            master_score=87.0,
            master_direction="BULLISH",
            signal="BUY",
            trade_action="BUY",
            decision_ready=True,
            decision_state="BUY_READY",
            operational_status="READY",
            data_quality="priced",
        )
        def pass_through(rows):
            return rows

        with patch.object(ranking, "get_snapshot_info", return_value={"signals": 1, "age_seconds": 1}), patch.object(
            ranking, "get_snapshot_signals", return_value=[row]
        ), patch.object(ranking, "ensure_institutional_ranking_rows", side_effect=pass_through), patch.object(
            ranking, "ensure_historical_confidence_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_operational_rules_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_institutional_conviction_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_institutional_priority_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_final_decision_rows", side_effect=pass_through
        ):
            result = ranking._normalize_snapshot_ranking()

        self.assertEqual(result[0]["score"], 8.7)
        self.assertEqual(result[0]["master_score"], 8.7)
        self.assertEqual(result[0]["master_score_raw"], 87.0)
        self.assertEqual(result[0]["master_score_source_scale"], "0_100")

    def test_snapshot_ranking_preserves_already_normalized_master_score(self):
        row = _bullish_decision_row(
            canonical_symbol="PETR4",
            master_score=8.7,
            master_score_source_scale="0_10",
            master_direction="BULLISH",
            signal="BUY",
            trade_action="BUY",
            decision_ready=True,
            decision_state="BUY_READY",
            operational_status="READY",
            data_quality="priced",
        )
        def pass_through(rows):
            return rows

        with patch.object(ranking, "get_snapshot_info", return_value={"signals": 1, "age_seconds": 1}), patch.object(
            ranking, "get_snapshot_signals", return_value=[row]
        ), patch.object(ranking, "ensure_institutional_ranking_rows", side_effect=pass_through), patch.object(
            ranking, "ensure_historical_confidence_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_operational_rules_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_institutional_conviction_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_institutional_priority_rows", side_effect=pass_through
        ), patch.object(
            ranking, "ensure_final_decision_rows", side_effect=pass_through
        ):
            result = ranking._normalize_snapshot_ranking()

        self.assertEqual(result[0]["score"], 8.7)
        self.assertEqual(result[0]["master_score"], 8.7)
        self.assertIsNone(result[0].get("master_score_raw"))
        self.assertEqual(result[0]["master_score_source_scale"], "0_10")

    def test_external_ranking_fallback_caches_display_score_contract(self):
        isolated_cache = {"data": None, "timestamp": 0.0, "snapshot_signature": None}
        with patch.object(ranking, "_RANK_CACHE", isolated_cache), patch.object(
            ranking, "get_snapshot_info", return_value={"signals": 0, "timestamp": "mission31c"}
        ), patch.object(ranking, "get_snapshot_signals", return_value=[]), patch.object(
            ranking, "ALLOW_NETWORK_FALLBACK", True
        ), patch.object(
            ranking, "current_provider_call_source", return_value="worker"
        ), patch.object(
            ranking, "fetch_market_data", return_value={"TST": object()}
        ), patch.object(
            ranking, "SYMBOLS", ["TST"]
        ), patch.object(
            ranking, "_get_symbol_frame", return_value=object()
        ), patch.object(
            ranking, "calculate_score", return_value={"symbol": "TST", "score": 87.0}
        ):
            result = ranking.generate_ranking(force_refresh=True, allow_external_fetch=True)

        self.assertEqual(result[0]["score"], 8.7)
        self.assertEqual(result[0]["master_score"], 8.7)
        self.assertEqual(result[0]["master_score_raw"], 87.0)
        self.assertEqual(result[0]["master_score_source_scale"], "0_100")
        self.assertEqual(isolated_cache["data"][0]["score"], 8.7)
        self.assertEqual(isolated_cache["data"][0]["master_score"], 8.7)
        self.assertEqual(isolated_cache["data"][0]["master_score_raw"], 87.0)
        self.assertEqual(isolated_cache["data"][0]["master_score_source_scale"], "0_100")

    def test_external_ranking_fallback_preserves_normalized_score_contract(self):
        isolated_cache = {"data": None, "timestamp": 0.0, "snapshot_signature": None}
        with patch.object(ranking, "_RANK_CACHE", isolated_cache), patch.object(
            ranking, "get_snapshot_info", return_value={"signals": 0, "timestamp": "mission31c-normalized"}
        ), patch.object(ranking, "get_snapshot_signals", return_value=[]), patch.object(
            ranking, "ALLOW_NETWORK_FALLBACK", True
        ), patch.object(
            ranking, "current_provider_call_source", return_value="worker"
        ), patch.object(
            ranking, "fetch_market_data", return_value={"TST": object()}
        ), patch.object(
            ranking, "SYMBOLS", ["TST"]
        ), patch.object(
            ranking, "_get_symbol_frame", return_value=object()
        ), patch.object(
            ranking,
            "calculate_score",
            return_value={"symbol": "TST", "score": 8.7, "master_score": 8.7, "master_score_source_scale": "0_10"},
        ):
            result = ranking.generate_ranking(force_refresh=True, allow_external_fetch=True)

        self.assertEqual(result[0]["score"], 8.7)
        self.assertEqual(result[0]["master_score"], 8.7)
        self.assertIsNone(result[0].get("master_score_raw"))
        self.assertEqual(result[0]["master_score_source_scale"], "0_10")
        self.assertEqual(isolated_cache["data"][0]["score"], 8.7)
        self.assertEqual(isolated_cache["data"][0]["master_score"], 8.7)
        self.assertIsNone(isolated_cache["data"][0].get("master_score_raw"))
        self.assertEqual(isolated_cache["data"][0]["master_score_source_scale"], "0_10")

    def test_score_display_uses_explicit_scale_and_never_maps_10_5_to_1(self):
        cases_0_10 = {
            9.5: (9.5, None),
            10.0: (10.0, None),
            10.5: (10.0, "master_score_display_clamped_above_10"),
            11.0: (10.0, "master_score_display_clamped_above_10"),
            15.0: (10.0, "master_score_display_clamped_above_10"),
            25.0: (10.0, "master_score_display_clamped_above_10"),
            85.0: (10.0, "master_score_display_clamped_above_10"),
            0.0: (0.0, None),
            None: (0.0, "master_score_display_invalid"),
            "": (0.0, "master_score_display_invalid"),
            "10.5": (10.0, "master_score_display_clamped_above_10"),
            "abc": (0.0, "master_score_display_invalid"),
            float("nan"): (0.0, "master_score_display_invalid"),
            float("inf"): (0.0, "master_score_display_invalid"),
        }
        self.assertEqual(normalize_master_score_display(True, source_scale="0_10"), (0.0, "master_score_display_invalid"))
        self.assertEqual(normalize_master_score_display(False, source_scale="0_10"), (0.0, "master_score_display_invalid"))
        for value, expected in cases_0_10.items():
            with self.subTest(value=repr(value), source_scale="0_10"):
                self.assertEqual(normalize_master_score_display(value, source_scale="0_10"), expected)

        cases_0_100 = {
            9.5: 1.0,
            10.0: 1.0,
            10.5: 1.1,
            11.0: 1.1,
            15.0: 1.5,
            25.0: 2.5,
            85.0: 8.5,
            0.0: 0.0,
        }
        for value, expected in cases_0_100.items():
            with self.subTest(value=value, source_scale="0_100"):
                self.assertEqual(normalize_master_score_display(value, source_scale="0_100")[0], expected)

        self.assertEqual(normalize_master_score_display(120.0, source_scale="0_100"), (0.0, "master_score_display_invalid"))
        self.assertEqual(normalize_master_score_display(True, source_scale="0_100"), (0.0, "master_score_display_invalid"))

        with self.assertRaises(ValueError):
            normalize_master_score_display(8.5, source_scale="legacy")

        with self.assertRaises(TypeError):
            normalize_master_score_display(8.5)
        with self.assertRaises(TypeError):
            normalize_master_score_display(8.5, "0_100")

        payload = attach_master_score_display_contract({"master_score_raw": 85.0})
        self.assertEqual(payload["master_score"], 8.5)
        self.assertEqual(payload["master_score_raw"], 85.0)
        self.assertEqual(payload["master_score_source_scale"], "0_100")

        ambiguous_low_raw = attach_master_score_display_contract({"master_score_raw": 8.5})
        self.assertEqual(ambiguous_low_raw["master_score"], 0.9)
        self.assertEqual(ambiguous_low_raw["master_score_raw"], 8.5)
        self.assertEqual(ambiguous_low_raw["master_score_source_scale"], "0_100")

        score_scale_only_payload = attach_master_score_display_contract(
            {"master_score": 8.7, "score_source_scale": "0_100"}
        )
        self.assertEqual(score_scale_only_payload["master_score"], 8.7)
        self.assertEqual(score_scale_only_payload["master_score_source_scale"], "0_10")

        out_of_range_raw = attach_master_score_display_contract({"master_score_raw": 150.0})
        self.assertEqual(out_of_range_raw["master_score"], 0.0)
        self.assertNotIn("master_score_raw", out_of_range_raw)
        self.assertEqual(out_of_range_raw["master_score_source_scale"], "0_10")
        self.assertEqual(out_of_range_raw["master_score_display_warning"], "master_score_display_invalid")
        self.assertEqual(resolve_master_score_display_value(out_of_range_raw), (None, None, None))
        repeated_out_of_range_raw = attach_master_score_display_contract(out_of_range_raw)
        self.assertEqual(repeated_out_of_range_raw["master_score_display_warning"], "master_score_display_invalid")
        self.assertEqual(repeated_out_of_range_raw["master_score_source_scale"], "0_10")

        invalid_raw_with_valid_fallback = attach_master_score_display_contract(
            {"master_score_raw": 150.0, "master_score": 8.7, "score": 8.7}
        )
        self.assertEqual(invalid_raw_with_valid_fallback["master_score"], 8.7)
        self.assertNotIn("master_score_display_warning", invalid_raw_with_valid_fallback)

        clamped_payload = attach_master_score_display_contract({"master_score": 10.5, "master_score_source_scale": "0_10"})
        repeated_clamped_payload = attach_master_score_display_contract(clamped_payload)
        self.assertEqual(repeated_clamped_payload["master_score"], 10.0)
        self.assertEqual(repeated_clamped_payload["master_score_display_warning"], "master_score_display_clamped_above_10")

        fallback_payload = attach_master_score_display_contract({"master_score_raw": "N/A", "master_score": 87.0})
        self.assertEqual(fallback_payload["master_score"], 8.7)
        self.assertEqual(fallback_payload["master_score_raw"], 87.0)
        self.assertEqual(fallback_payload["master_score_source_scale"], "0_100")
        self.assertEqual(fallback_payload["master_score_display_warning"], "master_score_normalized_from_raw_100")

        internal_low_raw = attach_master_score_display_contract(
            {"tool": "master_score", "master_score_raw": "N/A", "master_score": 8.0, "master_score_source_scale": "0_100"}
        )
        self.assertEqual(internal_low_raw["master_score"], 8.0)
        self.assertNotIn("master_score_raw", internal_low_raw)
        self.assertEqual(internal_low_raw["master_score_source_scale"], "0_10")
        self.assertNotIn("master_score_display_warning", internal_low_raw)

        fresh_payload = attach_master_score_display_contract(
            {
                "master_score": 8.5,
                "warnings": ["existing", "master_score_display_clamped_above_10"],
                "master_score_display_warning": "master_score_display_clamped_above_10",
                "master_score_block": {"score": 8.0, "score_warning": "master_score_display_invalid"},
            }
        )
        self.assertEqual(fresh_payload["warnings"], ["existing"])
        self.assertNotIn("master_score_display_warning", fresh_payload)
        self.assertNotIn("score_warning", fresh_payload["master_score_block"])

        invalid_block_raw = attach_master_score_display_contract({"master_score_block": {"score_raw": 150.0}})
        self.assertNotIn("score_raw", invalid_block_raw["master_score_block"])
        self.assertEqual(invalid_block_raw["master_score_block"]["score"], 0.0)
        self.assertEqual(invalid_block_raw["master_score_block"]["score_warning"], "master_score_display_invalid")
        self.assertEqual(invalid_block_raw["master_score_block"]["score_source_scale"], "0_10")
        self.assertNotIn("raw_score", invalid_block_raw["master_score_block"])
        repeated_invalid_block_raw = attach_master_score_display_contract(invalid_block_raw)
        self.assertEqual(repeated_invalid_block_raw["master_score_block"]["score_warning"], "master_score_display_invalid")

        ambiguous_low_block_raw = attach_master_score_display_contract({"master_score_block": {"score_raw": 8.0}})
        self.assertEqual(ambiguous_low_block_raw["master_score_block"]["score_raw"], 8.0)
        self.assertEqual(ambiguous_low_block_raw["master_score_block"]["score"], 0.8)
        self.assertEqual(ambiguous_low_block_raw["master_score_block"]["score_source_scale"], "0_100")

        display_scale_block = attach_master_score_display_contract(
            {"master_score_block": {"score": 87.0, "score_source_scale": "0_100"}}
        )
        self.assertEqual(display_scale_block["master_score_block"]["score"], 8.7)
        self.assertEqual(display_scale_block["master_score_block"]["score_warning"], "master_score_normalized_from_raw_100")
        self.assertEqual(display_scale_block["master_score_block"]["score_raw"], 87.0)
        raw_scale_block = attach_master_score_display_contract({"master_score_block": {"score_raw": 87.0}})
        self.assertEqual(raw_scale_block["master_score_block"]["score"], 8.7)
        self.assertEqual(raw_scale_block["master_score_block"]["score_raw"], 87.0)

    def test_snapshot_contract_blocks_claimed_display_score_above_ten(self):
        source_row = _final_decision_row(master_score=10.5, master_score_source_scale="0_10")
        display_row = attach_master_score_display_contract(
            source_row
        )
        envelope = build_decision_envelope(source_row)

        self.assertEqual(display_row["master_score"], 10.0)
        self.assertEqual(display_row["master_score_display_warning"], "master_score_display_clamped_above_10")
        self.assertEqual(envelope["decision_status"], DECISION_BLOCKED)
        self.assertFalse(envelope["decision_ready"])
        self.assertIn("master_score_display_clamped_above_10", envelope["blockers"])
        self.assertEqual(envelope["blocking_warnings"], ["master_score_display_clamped_above_10"])
        self.assertTrue(has_blocking_reasons(envelope))
        self.assertTrue(has_blocking_reasons({"master_score": 10.5, "master_score_source_scale": "0_10"}))
        self.assertTrue(has_blocking_reasons({"decision_envelope": {"blockers": ["snapshot_stale"]}}))
        self.assertTrue(has_blocking_reasons({"decision_envelope": {"warnings": ["master_score_display_invalid"]}}))
        self.assertTrue(has_blocking_reasons({"warnings": ["master_score_display_clamped_above_10"]}))
        self.assertFalse(has_blocking_reasons({"warnings": ["master_score_normalized_from_raw_100"]}))
        self.assertFalse(is_actionable_snapshot_row(source_row))

        non_operational = build_decision_envelope(_final_decision_row(master_score_raw=87.0, master_score=87.0))
        self.assertEqual(non_operational["decision_status"], "READY")
        self.assertIn("master_score_normalized_from_raw_100", non_operational["warnings"])
        self.assertEqual(non_operational["blocking_warnings"], [])

        invalid_raw = build_decision_envelope(_final_decision_row(master_score_raw=150.0))
        self.assertIn("master_score_display_invalid", invalid_raw["blocking_warnings"])

    def test_performance_intelligence_uses_generic_source_scale_for_master_score(self):
        self.assertEqual(score_bucket({"master_score_raw": 8.0, "source_scale": "0_100"}), "0-4")
        self.assertEqual(score_bucket({"master_score": 8.0, "source_scale": "0_10"}), "7-8")

    def test_mobile_babel_does_not_use_deprecated_expo_router_babel_plugin(self):
        package = json.loads((REPO_ROOT / "apps" / "mobile" / "package.json").read_text(encoding="utf-8"))
        babel_config = (REPO_ROOT / "apps" / "mobile" / "babel.config.js").read_text(encoding="utf-8")

        self.assertIn("expo-router", package["dependencies"])
        self.assertNotIn("expo-router/babel", babel_config)
        self.assertIn("babel-preset-expo", babel_config)

    def test_ai_import_order_has_no_operational_rules_cycle(self):
        orders = (
            ("app.ai.operational_rules", "app.ai.strategic_panel"),
            ("app.ai.strategic_panel", "app.ai.operational_rules"),
        )
        for order in orders:
            script = "import importlib; " + "; ".join(f"importlib.import_module({name!r})" for name in order)
            try:
                result = subprocess.run(
                    [sys.executable, "-c", script],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except subprocess.TimeoutExpired as exc:
                self.fail(f"Import cycle probe timed out for order {order}: {exc}")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_trade_decision_precedence_matrix_is_explicit(self):
        cases = [
            ("A", _bullish_decision_row(trade_action="WATCH", signal=""), "BUY"),
            ("B", _bullish_decision_row(trade_action=None, signal="BUY"), "BUY"),
            ("C", _bullish_decision_row(trade_action="HOLD", signal="SELL"), "SELL"),
            ("D", _bearish_decision_row(trade_action="", signal="SHORT"), "SHORT"),
            ("E", _bullish_decision_row(trade_action="NO_TRADE", signal="BUY"), "BUY"),
            ("F", _bullish_decision_row(trade_action="BUY", signal="SELL"), "BUY"),
            ("G", _bullish_decision_row(trade_action=None, signal=None), "BUY"),
            ("H", _bullish_decision_row(trade_action="", signal=""), "BUY"),
            ("I", _bullish_decision_row(trade_action=0, signal="BUY"), "BUY"),
            ("J", _bullish_decision_row(trade_action=False, signal="SELL"), "SELL"),
            ("K", _bullish_decision_row(trade_action="NO_DECISION", signal="BUY"), "NO_DECISION"),
            ("L", _bullish_decision_row(trade_action="NO_DECISION", signal=""), "NO_DECISION"),
            ("M", _bullish_decision_row(trade_action="BUY", signal="BUY", source_signal="SHORT"), "NO_DECISION"),
        ]

        for label, row, expected in cases:
            with self.subTest(case=label):
                decision = summarize_trade_decision([row])
                self.assertEqual(decision["trade_action"], expected)

        stale_direction = summarize_trade_decision(
            [_bullish_decision_row(trade_action="HOLD", signal="BUY", trade_direction="short")]
        )
        self.assertEqual(stale_direction["trade_action"], "BUY")
        self.assertEqual(stale_direction["trade_direction"], "long")

    def test_missing_audit_score_preserves_neutral_fallback(self):
        missing = enrich_final_decision_rows([_final_decision_row()], record_metrics=False)[0][0]
        zero = enrich_final_decision_rows([_final_decision_row(audit_score=0.0)], record_metrics=False)[0][0]
        valid = enrich_final_decision_rows([_final_decision_row(audit_score=60.0)], record_metrics=False)[0][0]
        nested_audit = enrich_final_decision_rows(
            [_final_decision_row(audit_score="invalid", audit={"audit_score": 60.0})],
            record_metrics=False,
        )[0][0]
        nested_auditor = enrich_final_decision_rows(
            [_final_decision_row(audit_score="invalid", audit={"auditor_score": 60.0})],
            record_metrics=False,
        )[0][0]
        bool_audit = enrich_final_decision_rows([_final_decision_row(audit_score=True)], record_metrics=False)[0][0]
        high_audit = enrich_final_decision_rows([_final_decision_row(audit_score=150.0)], record_metrics=False)[0][0]
        negative_audit = enrich_final_decision_rows([_final_decision_row(audit_score=-1.0)], record_metrics=False)[0][0]

        self.assertGreater(missing["final_decision_score"], zero["final_decision_score"])
        self.assertGreaterEqual(missing["final_decision_confidence"], zero["final_decision_confidence"])
        self.assertEqual(bool_audit["final_decision_score"], missing["final_decision_score"])
        self.assertEqual(high_audit["final_decision_score"], missing["final_decision_score"])
        self.assertEqual(negative_audit["final_decision_score"], missing["final_decision_score"])
        self.assertGreater(valid["final_decision_score"], missing["final_decision_score"])
        self.assertGreaterEqual(valid["final_decision_confidence"], missing["final_decision_confidence"])
        self.assertEqual(nested_audit["final_decision_score"], valid["final_decision_score"])
        self.assertEqual(nested_auditor["final_decision_score"], valid["final_decision_score"])

    def test_system_metrics_skip_invalid_master_score_average(self):
        from app.system import system_metrics

        isolated_metrics = dict(system_metrics._master_score_metrics)
        isolated_metrics.update(
            {
                "signals": 0,
                "approved": 0,
                "caution": 0,
                "blocked": 0,
                "bullish": 0,
                "bearish": 0,
                "neutral": 0,
                "average_master_score": 0.0,
                "updated_at": 0.0,
            }
        )
        with patch.object(system_metrics, "_master_score_metrics", isolated_metrics):
            system_metrics.record_master_score_metrics(
                [
                    {"master_score_raw": 87.0, "master_status": "approved", "master_direction": "bullish"},
                    {"master_score_raw": "invalid", "master_status": "approved", "master_direction": "bullish"},
                    {
                        "master_score_raw": "invalid",
                        "master_score": 92.0,
                        "master_score_source_scale": "0_100",
                        "master_status": "approved",
                        "master_direction": "bullish",
                    },
                    {
                        "master_score_raw": 8.0,
                        "master_score_source_scale": "0_100",
                        "master_status": "approved",
                        "master_direction": "bullish",
                    },
                ]
            )
            metrics = system_metrics.get_master_score_metrics_snapshot()

        self.assertEqual(metrics["signals"], 4)
        self.assertEqual(metrics["approved"], 4)
        self.assertEqual(metrics["bullish"], 4)
        self.assertEqual(metrics["average_master_score"], 6.23)

    def test_telegram_consumers_preserve_master_score_display_contract(self):
        from app.telegram import bot as telegram_bot

        signal = _final_decision_row(
            canonical_symbol="PETR4",
            master_score=87.0,
            master_score_raw=87.0,
            master_direction="BULLISH",
            master_status="APPROVED",
            final_decision="FINAL CONFIRMED",
            audit_status="APPROVED",
            conviction_level="VERY HIGH",
            priority_level="CRITICAL",
            historical_confidence_score=72.0,
        )

        message = format_signal_alert(signal)
        event = _event_payload(signal=signal, status="sent", reason="mission31c")

        self.assertIn("Score Mestre: 8.7", message)
        self.assertNotIn("Score Mestre: 87", message)
        self.assertEqual(event["master_score"], 8.7)
        self.assertEqual(event["master_score_raw"], 87.0)
        self.assertEqual(event["master_score_source_scale"], "0_100")

        display_only_event = _event_payload(
            signal={**signal, "master_score": 8.7, "master_score_raw": None, "master_score_source_scale": "0_10"},
            status="sent",
            reason="mission31c",
        )
        self.assertEqual(display_only_event["master_score"], 8.7)
        self.assertIsNone(display_only_event["master_score_raw"])

        invalid_message = format_signal_alert({**signal, "master_score_raw": "N/A", "master_score": "invalid"})
        self.assertIn("Score Mestre: N/A", invalid_message)
        self.assertEqual(
            _alert_priority_score_value({"master_score": 8.2, "master_score_source_scale": "0_10"}),
            82.0,
        )

        class FakeMessage:
            def __init__(self):
                self.reply_text = AsyncMock()

        message_gate = FakeMessage()
        update = SimpleNamespace(effective_user=SimpleNamespace(id=123), message=message_gate)
        denied_access = AsyncMock(return_value={"allowed": False})
        with patch.object(telegram_bot, "get_telegram_access", new=denied_access):
            access_result = __import__("asyncio").run(telegram_bot.require_access(update))

        self.assertIsNone(access_result)
        denied_access.assert_awaited_once_with(update)
        message_gate.reply_text.assert_awaited_once()

        allowed_message_gate = FakeMessage()
        allowed_update = SimpleNamespace(effective_user=SimpleNamespace(id=456), message=allowed_message_gate)
        allowed_access = AsyncMock(return_value={"allowed": True, "plan": "premium"})
        with patch.object(telegram_bot, "get_telegram_access", new=allowed_access):
            allowed_result = __import__("asyncio").run(telegram_bot.require_access(allowed_update))

        self.assertEqual(allowed_result, {"allowed": True, "plan": "premium"})
        allowed_access.assert_awaited_once_with(allowed_update)
        allowed_message_gate.reply_text.assert_not_awaited()

    def test_push_payload_uses_same_display_contract_as_body(self):
        signal = _final_decision_row(
            canonical_symbol="PETR4",
            master_score=87.0,
            master_score_raw=87.0,
            master_direction="BULLISH",
            master_status="APPROVED",
            final_decision="FINAL CONFIRMED",
            audit_status="APPROVED",
            conviction_level="VERY HIGH",
            priority_level="CRITICAL",
        )
        captured = {}

        class FakeQuery:
            def filter(self, *args, **kwargs):
                return self

            def all(self):
                return [type("User", (), {"id": 7})()]

        class FakeDb:
            def query(self, model):
                return FakeQuery()

            def close(self):
                return None

        def fake_send_push_notification(**kwargs):
            captured.update(kwargs)
            return {"sent": 1}

        with tempfile.TemporaryDirectory() as tempdir, patch.object(
            push_dispatcher, "PUSH_DISPATCH_STATE_PATH", Path(tempdir) / "push_state.json"
        ), patch.object(push_dispatcher, "SessionLocal", return_value=FakeDb()), patch.object(
            push_dispatcher, "get_push_token_store", return_value={"7": ["token"]}
        ), patch.object(
            push_dispatcher, "send_push_notification", side_effect=fake_send_push_notification
        ):
            result = push_dispatcher.dispatch_signal_pushes([signal])

        self.assertEqual(result["sent"], 1)
        self.assertIn("Score Mestre 8.7", captured["body"])
        self.assertEqual(captured["data"]["score"], "8.7")
        self.assertEqual(captured["data"]["master_score"], "8.7")
        self.assertEqual(captured["data"]["master_score_raw"], "87.0")
        self.assertEqual(captured["data"]["master_score_raw_source_scale"], "0_100")
        self.assertEqual(captured["data"]["master_score_source_scale"], "0_100")

        invalid_signal = _final_decision_row(
            canonical_symbol="VALE3",
            ticker="VALE3",
            symbol="VALE3",
            master_score=150.0,
            master_score_raw=150.0,
            score=150.0,
            master_direction="BULLISH",
            master_status="APPROVED",
            final_decision="FINAL CONFIRMED",
            audit_status="APPROVED",
            conviction_level="VERY HIGH",
            priority_level="CRITICAL",
        )
        with tempfile.TemporaryDirectory() as tempdir, patch.object(
            push_dispatcher, "PUSH_DISPATCH_STATE_PATH", Path(tempdir) / "push_state.json"
        ), patch.object(push_dispatcher, "SessionLocal", return_value=FakeDb()), patch.object(
            push_dispatcher, "get_push_token_store", return_value={"7": ["token"]}
        ), patch.object(push_dispatcher, "send_push_notification") as blocked_send:
            blocked_result = push_dispatcher.dispatch_signal_pushes([invalid_signal])

        self.assertEqual(blocked_result["sent"], 0)
        blocked_send.assert_not_called()

    def test_push_threshold_env_is_safe_and_legacy_compatible(self):
        self.assertEqual(push_dispatcher._score_threshold_from_env("nan"), 8.5)
        self.assertEqual(push_dispatcher._score_threshold_from_env("inf"), 8.5)
        self.assertEqual(push_dispatcher._score_threshold_from_env("-1"), 8.5)
        self.assertEqual(push_dispatcher._score_threshold_from_env("85"), 8.5)
        self.assertEqual(push_dispatcher._score_threshold_from_env("85.5"), 8.55)
        self.assertEqual(push_dispatcher._score_threshold_from_env("90"), 9.0)
        self.assertEqual(push_dispatcher._score_threshold_from_env("95"), 9.5)
        self.assertEqual(push_dispatcher._score_threshold_from_env("10.1"), 8.5)
        self.assertEqual(push_dispatcher._score_threshold_from_env("250"), 8.5)
        with patch.dict(os.environ, {"PUSH_MAX_SIGNALS_PER_CYCLE": "bad"}):
            self.assertEqual(push_dispatcher._positive_int_from_env("PUSH_MAX_SIGNALS_PER_CYCLE", 2, 1), 2)
        eligible_display = _final_decision_row(ticker="DSP85", master_score=8.5, score=8.5, master_score_source_scale="0_10")
        below_display = _final_decision_row(ticker="DSP84", master_score=8.4, score=8.4, master_score_source_scale="0_10")
        eligible_raw = _final_decision_row(ticker="RAW85", master_score=85.0, master_score_raw=85.0, score=85.0)
        below_raw = _final_decision_row(ticker="RAW84", master_score=84.4, master_score_raw=84.4, score=84.4)
        self.assertEqual(
            [item["ticker"] for item in push_dispatcher._eligible_signals([below_display, eligible_raw, below_raw, eligible_display])],
            ["RAW85", "DSP85"],
        )
        self.assertEqual(push_dispatcher._raw_master_score_source({"score": 87.0}), "0_100")
        self.assertEqual(push_dispatcher._raw_master_score_source({"master_score_raw": 8.2}), "0_100")
        self.assertEqual(
            push_dispatcher._raw_master_score_source({"master_score_raw": 8.2, "master_score_source_scale": "0_100"}),
            "0_100",
        )
        self.assertEqual(push_dispatcher._raw_master_score_source({"master_score_raw": float("nan"), "score": 87.0}), "0_100")
        self.assertEqual(push_dispatcher._raw_master_score_source({"master_score_raw": float("inf"), "score": 8.7}), "")
        self.assertEqual(push_dispatcher._raw_master_score_source({"master_score_raw": True}), "")
        self.assertEqual(push_dispatcher._raw_master_score_source({"master_score_raw": -1.0, "score": 8.7}), "")
        self.assertEqual(push_dispatcher._raw_master_score_source({"master_score_raw": 150.0, "score": 8.7}), "")
        self.assertEqual(
            push_dispatcher._raw_master_score_payload({"master_score": 87.0, "master_score_source_scale": "0_10"}),
            ("", ""),
        )
        self.assertEqual(
            push_dispatcher._raw_master_score_payload({"master_score": 8.7, "master_score_source_scale": "0_10"}),
            (87.0, "0_100"),
        )
        display_contract = attach_master_score_display_contract({"master_score_raw": 87.0})
        self.assertEqual(push_dispatcher._raw_master_score_source({"master_score_raw": "N/A", "score": 8.7}, display_contract), "0_100")
        self.assertEqual(
            push_dispatcher._raw_master_score_payload({"master_score_raw": "N/A", "score": 87.0})[1],
            "0_100",
        )

    def test_radar_sort_score_accepts_legacy_raw_master_score(self):
        self.assertEqual(web_radar._radar_sort_score({"master_score": 87.0}), 8.7)
        self.assertEqual(web_radar._radar_sort_score({"score": 86.0}), 8.6)
        self.assertEqual(web_radar._radar_sort_score({"master_score_raw": 150.0}), 0.0)


if __name__ == "__main__":
    unittest.main()
