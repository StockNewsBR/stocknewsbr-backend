import os
import time
import unittest
from unittest.mock import patch

from app.ai.final_decision import FINAL_CONFIRMED, FINAL_NO_TRADE
from app.ai.institutional_auditor import AUDIT_APPROVED
from app.ai.operational_rules import OPERATIONAL_BLOCKED, OPERATIONAL_READY
from app.api import routes_system
from app.cache.snapshot_cache import SnapshotCache
from app.engine.market_snapshot_engine import build_snapshot_payload
from app.services import workspace_service
from app.services.go_live_status_service import build_go_live_status
from app.services.institutional_consistency_audit import (
    ISSUE_APPROVED_OPERATIONAL_BLOCKED,
    REQUIRED_SIGNAL_CONTRACT_FIELDS,
    audit_institutional_consistency,
)
from app.system.observability_engine import build_observability_dashboard
from app.system.system_metrics import (
    get_metrics_snapshot,
    get_performance_metrics_snapshot,
    record_institutional_consistency_metrics,
)


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
        "data_quality": "priced",
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
        "strategic_panel": {
            "recommended_action": "OPORTUNIDADE CONFIRMADA",
            "strategic_panel_summary": "Contexto institucional favoravel.",
            "no_trade_now": False,
        },
        "strategic_panel_summary": "Contexto institucional favoravel.",
        "historical_confidence_score": 74.0,
        "historical_sample_size": 20,
        "historical_win_rate": 0.64,
        "operational_status": OPERATIONAL_READY,
        "operational_ready": True,
        "operational_blocks": [],
        "operational_block_reason": "",
        "conviction_level": "MUITO ALTA",
        "conviction_score": 88.0,
        "priority_level": "CRÍTICA",
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


def _healthy_snapshot():
    generated_at = time.time()
    rows = [_row("PETR4"), _row("VALE3")]
    audit = audit_institutional_consistency(rows, generated_at=generated_at)
    snapshot = {
        "signals": rows,
        "source": "engine",
        "stale": False,
        "timestamp": generated_at,
        "generated_at": generated_at,
        "institutional_consistency": audit,
        "institutional_consistency_metrics": audit["metrics"],
    }
    status = build_go_live_status(snapshot, now=generated_at)
    snapshot.update(
        {
            "snapshot_runtime_status": status["snapshot_runtime_status"],
            "snapshot_runtime": status["snapshot_runtime"],
            "go_live_ready": status["go_live_ready"],
            "go_live": status,
            "institutional_consistency_score": status["institutional_consistency_score"],
            "contract_coverage": status["contract_coverage"],
            "institutional_certified": status["institutional_certified"],
            "certification_timestamp": status["certification_timestamp"],
            "certification_reasons": status["certification_reasons"],
        }
    )
    return snapshot


class Mission24FGoLiveConsistencyTests(unittest.TestCase):
    def test_go_live_ready_uses_single_status_across_snapshot_routes_observability_and_workspace(self):
        snapshot = _healthy_snapshot()
        with patch.dict(os.environ, {"STOCKNEWSBR_TEST_MODE": "1", "SNAPSHOT_CACHE_FILE": ""}):
            cache = SnapshotCache()
            cache.update(snapshot)
            snapshot_info = cache.info()

        dashboard = build_observability_dashboard(
            snapshot=snapshot,
            ai_worker={"status": "warning"},
            providers={"items": [{"provider": "system", "status": "HEALTHY"}]},
            ranking={"status": "HEALTHY", "eligible": 2},
            radar={"status": "HEALTHY", "generated": 2},
            telegram={"status": "HEALTHY"},
            institutional_metrics=get_metrics_snapshot().get("institutional_metrics", {}),
            system_status={"status": "DEGRADED"},
        )

        self.assertEqual(snapshot["go_live_ready"], snapshot_info["go_live_ready"])
        self.assertEqual(snapshot["go_live_ready"], dashboard["go_live_ready"])
        self.assertEqual(snapshot["institutional_consistency_score"], dashboard["institutional_consistency_score"])

        bootstrap = {"brand": {}, "pricing": {}, "launch_roadmap": {}, "ai_modules": {}, "social_features": {}}
        metrics = {
            "engine_cycles": 1,
            "scan_time": 0.1,
            "signals_generated": 2,
            "assets_scanned": 2,
            "cache_age": 0,
            "workers": 1,
            "http_requests": 0,
            "http_errors": 0,
            "ws_connections": 0,
            "chat_messages": 0,
            "reports_created": 0,
            "uploads_completed": 0,
            "push_sends": 0,
            "worker_runtime": {},
            "institutional_metrics": get_metrics_snapshot().get("institutional_metrics", {}),
        }
        with patch.object(workspace_service, "get_public_bootstrap", return_value=bootstrap), patch.object(
            workspace_service, "get_metrics_snapshot", return_value=metrics
        ), patch.object(workspace_service, "get_snapshot", return_value=snapshot), patch.object(
            workspace_service, "get_snapshot_info", return_value=snapshot_info
        ), patch.object(workspace_service, "get_ranking", return_value=[]), patch.object(
            workspace_service, "get_posts", return_value=[]
        ), patch.object(workspace_service, "get_help_center_blueprint", return_value={"guides": []}), patch.object(
            workspace_service, "get_media_status", return_value={}
        ), patch.object(workspace_service, "get_push_status", return_value={}), patch.object(
            workspace_service, "get_user_workspace_layout", return_value={"tabs": [], "pinned_ticker": "PETR4"}
        ), patch.object(workspace_service, "list_room_messages", return_value=[]), patch.object(
            workspace_service, "persist_ai_alert_history", side_effect=lambda value: value
        ), patch.object(workspace_service.routes_system, "observability_dashboard", return_value=dashboard):
            workspace = workspace_service.get_workspace_data(user_id=7, channel="web")

        self.assertEqual(snapshot["go_live_ready"], workspace["go_live_ready"])
        self.assertEqual(workspace["go_live_ready"], workspace["status"]["go_live_ready"])
        self.assertEqual(workspace["go_live_ready"], workspace["market_snapshot"]["go_live_ready"])

        with patch.object(routes_system, "get_snapshot", return_value=snapshot), patch.object(
            routes_system, "get_snapshot_info", return_value=snapshot_info
        ), patch.object(routes_system, "get_metrics_snapshot", return_value=metrics), patch.object(
            routes_system, "get_storage_status", return_value={"ready": True}
        ), patch.object(routes_system, "get_media_status", return_value={"cdn_ready": True}), patch.object(
            routes_system, "get_push_status", return_value={"android_ready": True, "apple_ready": False}
        ), patch.object(routes_system, "get_moderation_summary", return_value={}):
            system_status = routes_system.system_status()
            readiness = routes_system.system_readiness()

        self.assertEqual(snapshot["go_live_ready"], system_status["go_live_ready"])
        self.assertEqual(snapshot["go_live_ready"], readiness["go_live_ready"])

    def test_snapshot_payload_has_complete_contracts_for_more_than_top_20_rows(self):
        rows = [_row(f"TEST{i:02d}") for i in range(25)]
        with patch("app.engine.market_snapshot_engine.get_market_pool", return_value={}):
            payload = build_snapshot_payload(rows, source="mission_24f", stale=False)

        self.assertEqual(payload["contract_coverage"]["coverage_pct"], 100.0)
        self.assertEqual(payload["contract_coverage"]["total"], 25)
        for row in payload["signals"]:
            missing = [field for field in REQUIRED_SIGNAL_CONTRACT_FIELDS if row.get(field) in (None, "", [], {})]
            self.assertEqual(missing, [], row.get("ticker"))

    def test_approved_operational_blocked_is_documented_not_false_positive(self):
        row = _row(
            "GGBR4",
            operational_status=OPERATIONAL_BLOCKED,
            operational_ready=False,
            operational_blocks=["liquidez insuficiente para operar agora"],
            final_decision=FINAL_NO_TRADE,
            final_decision_blocks=["bloqueio operacional"],
            ranking_eligible=False,
        )
        audit = audit_institutional_consistency([row], generated_at="now")
        issue_types = {issue["type"] for issue in audit["issues"]}

        self.assertNotIn(ISSUE_APPROVED_OPERATIONAL_BLOCKED, issue_types)
        self.assertEqual(audit["metrics"]["documented_operational_blocks"], 1)
        self.assertEqual(audit["documented_operational_blocks"][0]["operational_block_reason"], "liquidez insuficiente para operar agora")

    def test_missing_contracts_block_certification_and_reduce_score(self):
        incomplete = {"ticker": "MISS1", "symbol": "MISS1", "price": 10, "volume": 1000, "final_decision": FINAL_CONFIRMED}
        snapshot = {"signals": [incomplete], "source": "engine", "stale": False, "timestamp": time.time()}
        status = build_go_live_status(snapshot)

        self.assertFalse(status["go_live_ready"])
        self.assertFalse(status["institutional_certified"])
        self.assertIn("contracts_incomplete", status["reasons"])
        self.assertLess(status["institutional_consistency_score"], 95)

    def test_institutional_metrics_are_synchronized_between_snapshots(self):
        record_institutional_consistency_metrics(
            {
                "signals_checked": 2,
                "issues": 0,
                "contract_complete": 2,
                "contract_coverage_pct": 100.0,
                "consistency_score": 100.0,
            }
        )
        status_metrics = get_metrics_snapshot()
        performance = get_performance_metrics_snapshot()
        dashboard = build_observability_dashboard(
            snapshot=_healthy_snapshot(),
            ai_worker={"status": "ok"},
            providers={"items": [{"provider": "system", "status": "HEALTHY"}]},
            ranking={"status": "HEALTHY", "eligible": 2},
            radar={"status": "HEALTHY", "generated": 2},
            telegram={"status": "HEALTHY"},
            institutional_metrics=status_metrics["institutional_metrics"],
            system_status={"status": "HEALTHY"},
        )

        self.assertEqual(status_metrics["institutional_metrics"], performance["institutional_metrics"])
        self.assertEqual(status_metrics["institutional_metrics"], dashboard["institutional_metrics"])
        self.assertEqual(dashboard["operational_dashboard"]["consistency_score"], dashboard["institutional_consistency_score"])

    def test_certification_requires_go_live_and_no_critical_issue(self):
        healthy = build_go_live_status(_healthy_snapshot())
        blocked = build_go_live_status({"signals": [], "source": "empty", "stale": True})

        self.assertTrue(healthy["go_live_ready"])
        self.assertTrue(healthy["institutional_certified"])
        self.assertFalse(blocked["go_live_ready"])
        self.assertFalse(blocked["institutional_certified"])


if __name__ == "__main__":
    unittest.main()
