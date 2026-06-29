import os
import unittest
from unittest.mock import patch

import worker
from app.api import routes_system
from app.cache.snapshot_cache import SnapshotCache
from app.services import public_ai_tools_service, workspace_service
from app.services.snapshot_runtime_status import (
    SNAPSHOT_RUNTIME_CRITICAL,
    SNAPSHOT_RUNTIME_DEGRADED,
    SNAPSHOT_RUNTIME_HEALTHY,
    evaluate_go_live_ready,
    evaluate_snapshot_runtime_status,
)
from app.system.observability_engine import build_observability_dashboard
from app.system.system_metrics import get_worker_runtime_metrics_snapshot


def _row(ticker="PETR4"):
    return {
        "ticker": ticker,
        "symbol": ticker,
        "score": 91.0,
        "score_source_scale": "0_100",
        "master_score": 91.0,
        "master_score_raw": 91.0,
        "master_score_source_scale": "0_100",
        "ranking_opportunity_score": 91.0,
        "ranking_opportunity_source_scale": "0_100",
        "ranking_eligible": True,
        "signal": "BUY",
        "trade_action": "BUY",
        "decision_ready": True,
        "decision_state": "BUY_READY",
        "can_trade": True,
        "data_quality": "priced",
        "price": 37.5,
        "volume": 1_800_000,
        "source": "snapshot",
        "audit_status": "APPROVED",
        "auditor_status": "APPROVED",
        "blocked_by_auditor": False,
        "master_direction": "BULLISH",
        "master_status": "APPROVED",
        "master_conviction": "Alta",
        "master_confidence": "Alta",
        "strategic_panel": {
            "recommended_action": "OPORTUNIDADE CONFIRMADA",
            "strategic_panel_summary": "Contexto institucional favoravel.",
        },
        "historical_confidence_score": 74.0,
        "operational_status": "READY",
        "operational_ready": True,
        "operational_blocks": [],
        "conviction_level": "MUITO ALTA",
        "priority_level": "CRÍTICA",
        "radar_no_trade_now": False,
        "final_decision": "🟢 OPORTUNIDADE CONFIRMADA",
        "final_decision_blocks": [],
    }


def _tools():
    tools = public_ai_tools_service._empty_tools()
    tools["risk"] = [_row()]
    return tools


class SingleCycleStopEvent:
    def __init__(self):
        self.wait_calls = 0

    def is_set(self):
        return self.wait_calls > 0

    def wait(self, timeout):
        self.wait_calls += 1
        return True


class Mission24CGoLiveRuntimeTests(unittest.TestCase):
    def test_snapshot_runtime_status_classifies_empty_healthy_and_degraded(self):
        empty = evaluate_snapshot_runtime_status({"signals": [], "source": "empty", "stale": True})
        healthy = evaluate_snapshot_runtime_status({"signals": [_row()], "source": "engine", "stale": False, "timestamp": 2_000_000_000})
        fallback = evaluate_snapshot_runtime_status({"signals": [_row()], "source": "snapshot_fallback", "stale": True, "timestamp": 2_000_000_000})

        self.assertEqual(empty["status"], SNAPSHOT_RUNTIME_CRITICAL)
        self.assertIn("signals_empty", empty["reasons"])
        self.assertEqual(healthy["status"], SNAPSHOT_RUNTIME_HEALTHY)
        self.assertEqual(fallback["status"], SNAPSHOT_RUNTIME_DEGRADED)
        self.assertTrue(fallback["fallback_active"])

    def test_snapshot_cache_tracks_last_good_and_runtime_health_in_test_file(self):
        with patch.dict(os.environ, {"STOCKNEWSBR_TEST_MODE": "1", "SNAPSHOT_CACHE_FILE": ""}):
            cache = SnapshotCache()
            cache.update({"signals": [_row()], "source": "engine", "stale": False})
            info = cache.info()
            last_good = cache.get_last_good()

        self.assertEqual(info["snapshot_runtime_status"], SNAPSHOT_RUNTIME_HEALTHY)
        self.assertEqual(info["last_good_signals"], 1)
        self.assertEqual(info["last_good_snapshot"]["signals"], 1)
        self.assertEqual(last_good["signals"][0]["ticker"], "PETR4")

    def test_public_ai_tools_uses_last_good_snapshot_when_current_is_unavailable(self):
        with patch.object(public_ai_tools_service, "get_snapshot", return_value={"ai_tools": {}, "source": "empty"}), patch.object(
            public_ai_tools_service,
            "get_last_good_snapshot",
            return_value={"ai_tools": _tools(), "generated_at": "2026-06-12T10:00:00+00:00"},
        ):
            payload = public_ai_tools_service.build_public_ai_tools_payload()

        self.assertEqual(payload["source"], "last_good_snapshot")
        self.assertTrue(payload["using_fallback"])
        self.assertEqual(payload["tools"]["risk"][0]["ticker"], "PETR4")

    def test_observability_marks_empty_snapshot_critical_and_blocks_go_live(self):
        dashboard = build_observability_dashboard(
            snapshot={"signals": 0, "source": "empty", "stale": True},
            ai_worker={"status": "ok"},
            providers={"items": [{"provider": "system", "status": "HEALTHY"}]},
            ranking={"status": "HEALTHY", "eligible": 1},
            radar={"status": "HEALTHY", "generated": 1},
            telegram={"status": "HEALTHY"},
            system_status={"status": "HEALTHY"},
        )

        self.assertEqual(dashboard["snapshot_runtime_status"], SNAPSHOT_RUNTIME_CRITICAL)
        self.assertEqual(dashboard["snapshot_health"]["status"], SNAPSHOT_RUNTIME_CRITICAL)
        self.assertFalse(dashboard["go_live_ready"])

    def test_go_live_ready_requires_healthy_snapshot_worker_and_observability(self):
        runtime = evaluate_snapshot_runtime_status({"signals": [_row()], "source": "engine", "stale": False, "timestamp": 2_000_000_000})

        self.assertTrue(evaluate_go_live_ready(runtime, worker_status="ok", observability_status="HEALTHY")["go_live_ready"])
        self.assertFalse(evaluate_go_live_ready(runtime, worker_status="idle", observability_status="HEALTHY")["go_live_ready"])
        self.assertFalse(
            evaluate_go_live_ready(
                {"status": SNAPSHOT_RUNTIME_DEGRADED, "signals": 1, "fallback_active": True},
                worker_status="ok",
                observability_status="HEALTHY",
            )["go_live_ready"]
        )

    def test_worker_records_generation_success_and_failure(self):
        success_before = get_worker_runtime_metrics_snapshot()
        healthy_payload = {
            "signals": [_row()],
            "source": "engine",
            "stale": False,
            "snapshot_runtime_status": SNAPSHOT_RUNTIME_HEALTHY,
            "snapshot_runtime": {"status": SNAPSHOT_RUNTIME_HEALTHY, "signals": 1, "fallback_active": False},
        }
        with patch.object(worker, "safe_run_engine", return_value=[_row()]), patch.object(
            worker, "generate_market_snapshot", return_value=healthy_payload
        ), patch.object(worker, "dispatch_signal_pushes"), patch.object(worker, "send_bulk_alert"), patch.object(
            worker, "_prewarm_public_quotes"
        ), patch.object(worker, "_prewarm_public_charts"), patch.object(worker, "_prewarm_public_news"), patch.object(worker, "set_workers"):
            worker.worker_loop(SingleCycleStopEvent())

        with patch.object(worker, "safe_run_engine", return_value=[_row()]), patch.object(
            worker, "generate_market_snapshot", side_effect=RuntimeError("boom")
        ), patch.object(worker, "_prewarm_public_quotes"), patch.object(worker, "_prewarm_public_charts"), patch.object(
            worker, "_prewarm_public_news"
        ), patch.object(worker, "set_workers"):
            worker.worker_loop(SingleCycleStopEvent())

        after = get_worker_runtime_metrics_snapshot()
        self.assertGreater(after["worker_generation_success"], success_before["worker_generation_success"])
        self.assertGreater(after["worker_generation_failure"], success_before["worker_generation_failure"])

    def test_routes_and_workspace_expose_runtime_and_go_live_contracts(self):
        snapshot_info = {
            "signals": 1,
            "timestamp": 2_000_000_000,
            "age_seconds": 0,
            "has_signals": True,
            "is_empty": False,
            "source": "engine",
            "stale": False,
            "snapshot_runtime_status": SNAPSHOT_RUNTIME_HEALTHY,
            "snapshot_runtime": {"status": SNAPSHOT_RUNTIME_HEALTHY, "signals": 1, "fallback_active": False},
            "last_good_signals": 1,
            "last_good_timestamp": 2_000_000_000,
        }
        system_snapshot = {
            "signals": [_row()],
            "source": "engine",
            "stale": False,
            "generated_at": 2_000_000_000,
            "go_live_ready": True,
            "institutional_certified": True,
            "institutional_consistency_score": 100.0,
            "contract_coverage": {"total": 1, "complete": 1, "missing": 0, "coverage_pct": 100.0},
        }
        with patch.object(routes_system, "get_ai_worker_report", return_value={"status": "ok"}), patch.object(
            routes_system, "get_ai_tab_audit_report", return_value={"overall_status": "ok", "release_decision": {"go_live": True}, "batch_summary": {"approved_tools": 1}}
        ), patch.object(routes_system, "get_snapshot_info", return_value=snapshot_info), patch.object(
            routes_system, "get_snapshot", return_value=system_snapshot
        ), patch.object(
            routes_system, "get_poll_store_summary", return_value={"current_week_polls": 1}
        ):
            health = routes_system.system_health()

        self.assertEqual(health["snapshot"]["snapshot_runtime_status"], SNAPSHOT_RUNTIME_HEALTHY)
        self.assertTrue(health["go_live_ready"])
        self.assertTrue(health["institutional_certified"])
        self.assertEqual(health["institutional_consistency_score"], 100.0)
        self.assertEqual(health["contract_coverage"]["coverage_pct"], 100.0)

        snapshot = {"signals": [_row()], "source": "engine", "stale": False, "ai_tools": _tools(), "symbol_snapshots": {}}
        observability = {
            "system_status": "HEALTHY",
            "snapshot_runtime_status": SNAPSHOT_RUNTIME_HEALTHY,
            "snapshot_runtime": {"status": SNAPSHOT_RUNTIME_HEALTHY, "signals": 1, "fallback_active": False},
            "go_live_ready": True,
            "go_live": {
                "go_live_ready": True,
                "reasons": [],
                "institutional_certified": True,
                "institutional_consistency_score": 100.0,
                "contract_coverage": {"total": 1, "complete": 1, "missing": 0, "coverage_pct": 100.0},
            },
            "operational_dashboard": {"worker_status": "ok"},
        }
        bootstrap = {"brand": {}, "pricing": {}, "launch_roadmap": {}, "ai_modules": {}, "social_features": {}}
        metrics = {"engine_cycles": 1, "signals_generated": 1, "assets_scanned": 1, "cache_age": 0, "http_requests": 0, "ws_connections": 0, "chat_messages": 0}
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
        ), patch.object(workspace_service.routes_system, "observability_dashboard", return_value=observability):
            payload = workspace_service.get_workspace_data(user_id=7, channel="web")

        self.assertEqual(payload["snapshot_runtime_status"], SNAPSHOT_RUNTIME_HEALTHY)
        self.assertEqual(payload["market_snapshot"]["snapshot_runtime_status"], SNAPSHOT_RUNTIME_HEALTHY)
        self.assertTrue(payload["go_live_ready"])
        self.assertTrue(payload["institutional_certified"])
        self.assertTrue(payload["market_snapshot"]["institutional_certified"])
        self.assertEqual(payload["institutional_consistency_score"], 100.0)
        self.assertEqual(payload["contract_coverage"]["coverage_pct"], 100.0)
        self.assertEqual(payload["market_snapshot"]["institutional_consistency_score"], 100.0)
        self.assertEqual(payload["market_snapshot"]["contract_coverage"]["coverage_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
