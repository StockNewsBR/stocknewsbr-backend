import json
import os
from contextlib import ExitStack
from pathlib import Path
import unittest
from unittest.mock import patch

from app.ai.final_decision import FINAL_CONFIRMED, FINAL_NO_TRADE
from app.ai.institutional_auditor import AUDIT_APPROVED, AUDIT_BLOCKED
from app.ai.institutional_conviction import CONVICTION_VERY_HIGH
from app.ai.institutional_priority import PRIORITY_CRITICAL
from app.ai.institutional_radar import institutional_radar_items
from app.ai.institutional_ranking import institutional_ranking_items
from app.ai.operational_rules import OPERATIONAL_BLOCKED, OPERATIONAL_READY
from app.api import routes_system
from app.cache.snapshot_cache import SnapshotCache
from app.engine.market_snapshot_engine import build_snapshot_payload
from app.services import ranking, workspace_service
from app.services.institutional_consistency_audit import (
    ISSUE_APPROVED_OPERATIONAL_BLOCKED,
    ISSUE_DIRECTION_CONFLICT,
    ISSUE_PRIORITY_NO_TRADE,
    audit_institutional_consistency,
)
from app.system import push_dispatcher
from app.system.system_metrics import (
    get_metrics_snapshot,
    record_institutional_auditor_metrics,
    record_institutional_consistency_metrics,
    record_master_score_metrics,
)
from app.telegram.telegram_alert_engine import build_telegram_alert


ROOT = Path(__file__).resolve().parents[1]


def _row(ticker="PETR4", **overrides):
    base = {
        "ticker": ticker,
        "symbol": ticker,
        "score": 91.0,
        "signal": "BUY",
        "trade_action": "BUY",
        "decision_ready": True,
        "decision_state": "BUY_READY",
        "can_trade": True,
        "data_quality": "cached",
        "price": 37.5,
        "volume": 1_800_000,
        "audit_status": AUDIT_APPROVED,
        "auditor_status": AUDIT_APPROVED,
        "audit_score": 94.0,
        "audit_blocks": [],
        "blocked_by_auditor": False,
        "master_score": 92.0,
        "master_direction": "BULLISH",
        "master_conviction": "Alta",
        "master_confidence": "Alta",
        "master_status": AUDIT_APPROVED,
        "master_risk": "Baixo",
        "master_summary": "Fluxo comprador e liquidez adequada.",
        "master_reasoning": {
            "flow_reason": "Fluxo comprador institucional.",
            "smart_money_reason": "Smart Money positivo.",
        },
        "strategic_panel": {
            "recommended_action": "OPORTUNIDADE CONFIRMADA",
            "strategic_panel_summary": "Contexto institucional favoravel.",
            "no_trade_now": False,
            "risk_block": {"level": "Baixo", "score": 20},
        },
        "strategic_panel_summary": "Contexto institucional favoravel.",
        "recommended_action": "OPORTUNIDADE CONFIRMADA",
        "historical_confidence_score": 74.0,
        "historical_sample_size": 20,
        "historical_win_rate": 0.64,
        "operational_status": OPERATIONAL_READY,
        "operational_ready": True,
        "operational_blocks": [],
        "conviction_level": CONVICTION_VERY_HIGH,
        "conviction_score": 88.0,
        "priority_level": PRIORITY_CRITICAL,
        "priority_score": 91.0,
        "ranking_eligible": True,
        "ranking_opportunity_score": 92.0,
        "radar_no_trade_now": False,
        "radar_prioritization_score": 91.0,
        "final_decision": FINAL_CONFIRMED,
        "final_decision_score": 92.0,
        "final_decision_confidence": "Alta",
        "final_decision_blocks": [],
    }
    base.update(overrides)
    return base


def _workspace_dependencies(snapshot, observability=None):
    bootstrap = {
        "brand": "StockNewsBR",
        "pricing": {"trial_days": 30},
        "launch_roadmap": {},
        "ai_modules": [],
        "social_features": {},
    }
    metrics = {
        "engine_cycles": 1,
        "signals_generated": len(snapshot.get("signals", [])),
        "assets_scanned": len(snapshot.get("signals", [])),
        "cache_age": 0,
        "http_requests": 0,
        "ws_connections": 0,
        "chat_messages": 0,
    }
    stack = ExitStack()
    stack.enter_context(patch.object(workspace_service, "get_public_bootstrap", return_value=bootstrap))
    stack.enter_context(patch.object(workspace_service, "get_metrics_snapshot", return_value=metrics))
    stack.enter_context(patch.object(workspace_service, "get_snapshot", return_value=snapshot))
    stack.enter_context(patch.object(workspace_service, "get_ranking", return_value=[]))
    stack.enter_context(patch.object(workspace_service, "get_posts", return_value=[]))
    stack.enter_context(patch.object(workspace_service, "get_help_center_blueprint", return_value={"guides": []}))
    stack.enter_context(patch.object(workspace_service, "get_media_status", return_value={}))
    stack.enter_context(patch.object(workspace_service, "get_push_status", return_value={}))
    stack.enter_context(patch.object(workspace_service, "get_user_workspace_layout", return_value={"tabs": ["home"], "pinned_ticker": "PETR4", "opened_popouts": []}))
    stack.enter_context(patch.object(workspace_service, "get_layout", return_value={"tabs": [{"id": "home", "title": "Home"}]}))
    stack.enter_context(patch.object(workspace_service, "list_room_messages", return_value=[]))
    stack.enter_context(patch.object(workspace_service, "persist_ai_alert_history", side_effect=lambda value: value))
    stack.enter_context(patch.object(workspace_service.routes_system, "observability_dashboard", return_value=observability or {}))
    return stack


class Mission24BHardeningTests(unittest.TestCase):
    def test_snapshot_cache_uses_temporary_file_under_tests(self):
        real_snapshot = ROOT / "runtime" / "cache" / "snapshot.json"
        with patch.dict(os.environ, {"STOCKNEWSBR_TEST_MODE": "1", "SNAPSHOT_CACHE_FILE": ""}):
            cache = SnapshotCache()
            cache.update({"signals": [_row("BLOCKED")], "source": "unit_test", "stale": False})

        self.assertNotEqual(cache._storage_path.resolve(), real_snapshot.resolve())
        if real_snapshot.exists():
            payload = json.loads(real_snapshot.read_text(encoding="utf-8"))
            tickers = _snapshot_identity_values(payload)
            self.assertFalse({"BLOCKED", "WATCH1", "TEST", "FAKE", "MOCK"} & tickers)

    def test_snapshot_payload_exposes_complete_institutional_root_contracts(self):
        with patch("app.engine.market_snapshot_engine.get_market_pool", return_value={}):
            payload = build_snapshot_payload([_row()], source="mission_24b")

        for key in (
            "auditor",
            "master_score",
            "strategic_panel",
            "institutional_radar",
            "institutional_ranking",
            "historical_confidence",
            "operational_rules",
            "institutional_conviction",
            "institutional_priority",
            "final_decision",
        ):
            self.assertIn(key, payload)

        self.assertIsInstance(payload["institutional_conviction"], dict)
        self.assertIsInstance(payload["institutional_priority"], dict)
        self.assertIsInstance(payload["final_decision"], dict)
        self.assertIn("institutional_consistency", payload)

    def test_workspace_blocked_signals_include_operational_final_radar_and_readiness_reasons(self):
        blocked = _row(
            "BLOCKED",
            audit_status=AUDIT_BLOCKED,
            auditor_status=AUDIT_BLOCKED,
            blocked_by_auditor=True,
            audit_blocks=["Auditor BLOCKED"],
            master_status=AUDIT_BLOCKED,
        )
        watch = _row(
            "WATCH1",
            signal="WATCH_BUY",
            trade_action="WATCH_BUY",
            decision_ready=False,
            decision_state="WAIT",
            final_decision=FINAL_NO_TRADE,
            final_decision_blocks=["Final Decision NAO OPERAR AGORA"],
            radar_no_trade_now=True,
            radar_blocked_reasons=["Radar NO_TRADE"],
            operational_status=OPERATIONAL_BLOCKED,
            operational_blocks=["Operational BLOCKED"],
        )
        snapshot = {"signals": [blocked, watch], "ai_tools": workspace_service._empty_ai_outputs(), "symbol_snapshots": {}}

        with _workspace_dependencies(snapshot):
            payload = workspace_service.get_workspace_data(user_id=7, channel="web")

        blocked_by_ticker = {row["ticker"]: row for row in payload["blocked_signals"]}
        self.assertIn("BLOCKED", blocked_by_ticker)
        self.assertIn("WATCH1", blocked_by_ticker)
        self.assertIn("Auditor BLOCKED", blocked_by_ticker["BLOCKED"]["workspace_block_reasons"])
        self.assertIn("Operational BLOCKED", blocked_by_ticker["WATCH1"]["workspace_block_reasons"])
        self.assertIn("Decision Ready False", blocked_by_ticker["WATCH1"]["workspace_block_reasons"])

    def test_metrics_dashboard_and_workspace_expose_institutional_metrics(self):
        record_institutional_auditor_metrics({"approved": 1, "caution": 0, "blocked": 1, "avg_audit_score": 74.0})
        record_master_score_metrics([_row(), _row("SHORT1", master_direction="BEARISH", trade_action="SHORT", signal="SHORT", decision_state="SHORT_READY")])
        record_institutional_consistency_metrics({"signals_checked": 2, "issues": 1, "direction_conflicts": 1})

        metrics = get_metrics_snapshot()
        for key in (
            "institutional_auditor",
            "master_score",
            "historical_confidence",
            "operational_rules",
            "institutional_conviction",
            "institutional_priority",
            "institutional_radar",
            "institutional_ranking",
            "final_decision",
            "telegram_alerts",
        ):
            self.assertIn(key, metrics)
            self.assertIn(key, metrics["institutional_metrics"])

        with patch.object(routes_system, "get_snapshot_info", return_value={"signals": 1, "invalid": 0, "discarded": 0, "blocked": 0, "master_scores": []}), patch.object(
            routes_system, "get_ai_worker_report", return_value={"status": "ok"}
        ), patch.object(routes_system, "get_ai_tab_audit_report", return_value={"overall_status": "ok", "batch_summary": {"approved_tools": 1, "blocked_tools": 0}}), patch.object(
            routes_system, "get_poll_store_summary", return_value={"current_week_polls": 1}
        ), patch.object(routes_system, "get_push_status", return_value={"android_ready": True}), patch.object(
            routes_system, "get_storage_status", return_value={"ready": True}
        ), patch.object(routes_system, "get_ranking", return_value=[{"ticker": "PETR4"}]), patch.object(
            routes_system, "get_telegram_health", return_value={"status": "HEALTHY"}
        ):
            dashboard = routes_system.observability_dashboard()

        self.assertIn("institutional_metrics", dashboard)
        self.assertIn("telegram_alerts", dashboard["institutional_metrics"])

        snapshot = {"signals": [_row()], "ai_tools": workspace_service._empty_ai_outputs(), "symbol_snapshots": {}}
        with _workspace_dependencies(snapshot, observability=dashboard):
            workspace = workspace_service.get_workspace_data(user_id=7, channel="web")
        self.assertIn("institutional_metrics", workspace["observability"])

    def test_blocked_rows_do_not_enter_promotional_surfaces(self):
        blocked = _row(
            "BLOCKED",
            audit_status=AUDIT_BLOCKED,
            auditor_status=AUDIT_BLOCKED,
            blocked_by_auditor=True,
            audit_blocks=["Auditor BLOCKED"],
            ranking_eligible=True,
            ranking_opportunity_score=99.0,
            radar_prioritization_score=99.0,
        )

        self.assertEqual(institutional_ranking_items([blocked]), [])
        self.assertEqual(institutional_radar_items([blocked]), [])
        self.assertEqual(push_dispatcher._eligible_signals([blocked]), [])
        self.assertEqual(build_telegram_alert(blocked)["status"], "blocked")

        with patch.object(ranking, "get_snapshot_info", return_value={"signals": 1, "timestamp": 1, "age_seconds": 0, "has_signals": True, "is_empty": False}), patch.object(
            ranking, "get_snapshot_signals", return_value=[blocked]
        ):
            self.assertEqual(ranking.get_ranking(force_refresh=True), [])

        snapshot = {"signals": [blocked, _row("PETR4")], "ai_tools": workspace_service._empty_ai_outputs(), "symbol_snapshots": {}}
        with _workspace_dependencies(snapshot):
            workspace = workspace_service.get_workspace_data(user_id=7, channel="web")
        self.assertNotIn("BLOCKED", [row["ticker"] for row in workspace["top_signals"]])

    def test_consistency_audit_records_conflicts_without_changing_decisions(self):
        conflicting = _row("CONF1", master_direction="BULLISH", trade_action="SHORT", signal="SHORT", decision_state="SHORT_READY")
        critical_no_trade = _row("CRIT1", final_decision=FINAL_NO_TRADE, final_decision_blocks=["sem trade"])
        approved_operational_blocked = _row("OPER1", operational_status=OPERATIONAL_BLOCKED)
        original = dict(conflicting)

        audit = audit_institutional_consistency([conflicting, critical_no_trade, approved_operational_blocked], generated_at="now")
        issue_types = {issue["type"] for issue in audit["issues"]}

        self.assertIn(ISSUE_DIRECTION_CONFLICT, issue_types)
        self.assertIn(ISSUE_PRIORITY_NO_TRADE, issue_types)
        self.assertIn(ISSUE_APPROVED_OPERATIONAL_BLOCKED, issue_types)
        self.assertEqual(conflicting, original)

    def test_real_snapshot_file_has_no_synthetic_test_symbols(self):
        snapshot_file = ROOT / "runtime" / "cache" / "snapshot.json"
        if not snapshot_file.exists():
            self.skipTest("snapshot real ausente")

        payload = json.loads(snapshot_file.read_text(encoding="utf-8"))
        tickers = _snapshot_identity_values(payload)
        self.assertFalse({"BLOCKED", "WATCH1", "TEST", "FAKE", "MOCK"} & tickers)


def _snapshot_identity_values(payload):
    values = set()

    def visit(value):
        if isinstance(value, dict):
            for key in ("ticker", "symbol", "snapshot_id"):
                raw = value.get(key)
                if raw:
                    values.add(str(raw).upper())
            for key in ("signals", "leaders"):
                visit(value.get(key))
            by_ticker = value.get("by_ticker")
            if isinstance(by_ticker, dict):
                values.update(str(key).upper() for key in by_ticker.keys())
                visit(list(by_ticker.values()))
            visit(value.get("payload"))
            visit(value.get("last_good_payload"))
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    return values


if __name__ == "__main__":
    unittest.main()
