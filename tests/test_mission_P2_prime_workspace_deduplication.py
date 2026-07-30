"""P2' Workspace Service Deduplication Test

Tests that workspace data doesn't contain duplicate top-level fields
that mirror market_snapshot contents.
"""

import pytest
from unittest.mock import patch, MagicMock

from app.services.workspace_service import get_workspace_data


class TestP2PrimeWorkspaceDeduplication:
    """P2': Workspace service - remove duplicate top-level fields
    that mirror market_snapshot contents."""

    def test_no_top_level_duplicates_of_market_snapshot(self, monkeypatch):
        """Workspace response should not have top-level fields that duplicate market_snapshot."""
        # Mock all external dependencies
        mock_snapshot = {
            "schema_version": 1,
            "generated_at": 1234567890.0,
            "source": "engine_v36",
            "stale": False,
            "stats": {"total_signals": 5, "bullish": 3, "bearish": 2},
            "data_status": {"price": "ok", "volume": "ok"},
            "market_pulse": {"bias": "NEUTRO"},
            "auditor": {"status": "healthy"},
            "signals": [
                {
                    "ticker": "PETR4",
                    "symbol": "PETR4",
                    "score": 85,
                    "signal": "compra",
                    "master_verdict": "COMPRA",
                    "rsi": 65,
                    "price": 40.50,
                    "volume": 1000000,
                    "change_pct": 2.5,
                    "support": 39.0,
                    "resistance": 42.0,
                }
            ],
            "ai_tools": {"institutional_conviction": [], "institutional_priority": []},
        }

        def mock_get_snapshot():
            return mock_snapshot

        def mock_get_snapshot_info():
            return {
                "timestamp": 1234567890.0,
                "signals": 5,
                "last_good_signals": 5,
                "last_good_timestamp": 1234567890.0,
                "last_good_snapshot": {"signals": 5, "timestamp": 1234567890.0},
                "snapshot_runtime": {"status": "FRESH"},
            }

        def mock_get_metrics_snapshot():
            return {"institutional_metrics": {}}

        def mock_get_public_bootstrap():
            return {"brand": {"name": "StockNewsBR"}}

        def mock_get_layout():
            return {"tabs": [{"id": "home", "label": "Home"}]}

        def mock_get_ranking():
            return []

        def mock_get_posts(limit=10):
            return []

        def mock_persist_ai_alert_history(ai_outputs):
            return ai_outputs

        def mock_get_help_center_blueprint():
            return {}

        def mock_get_media_status():
            return {}

        def mock_get_push_status():
            return {}

        def mock_observability_dashboard():
            return {
                "snapshot_runtime": {"status": "FRESH"},
                "go_live": {"go_live_ready": True, "institutional_consistency_score": 80},
            }

        def mock_get_telegram_alert_history(limit=30):
            return []

        def mock_get_telegram_health():
            return {}

        def mock_get_user_workspace_layout(user_id):
            return {"tabs": [], "pinned_ticker": "PETR4"}

        # Patch all dependencies
        monkeypatch.setattr("app.services.workspace_service.get_snapshot", mock_get_snapshot)
        monkeypatch.setattr("app.services.workspace_service.get_snapshot_info", mock_get_snapshot_info)
        monkeypatch.setattr("app.services.workspace_service.get_metrics_snapshot", mock_get_metrics_snapshot)
        monkeypatch.setattr("app.services.workspace_service.get_public_bootstrap", mock_get_public_bootstrap)
        monkeypatch.setattr("app.services.workspace_service.get_layout", mock_get_layout)
        monkeypatch.setattr("app.services.workspace_service.get_ranking", mock_get_ranking)
        monkeypatch.setattr("app.services.workspace_service.get_posts", mock_get_posts)
        monkeypatch.setattr("app.services.workspace_service.persist_ai_alert_history", mock_persist_ai_alert_history)
        monkeypatch.setattr("app.services.workspace_service.get_help_center_blueprint", mock_get_help_center_blueprint)
        monkeypatch.setattr("app.services.workspace_service.get_media_status", mock_get_media_status)
        monkeypatch.setattr("app.services.workspace_service.get_push_status", mock_get_push_status)
        monkeypatch.setattr("app.api.routes_system.observability_dashboard", mock_observability_dashboard)
        monkeypatch.setattr("app.telegram.telegram_alert_engine.get_telegram_alert_history", mock_get_telegram_alert_history)
        monkeypatch.setattr("app.telegram.telegram_alert_engine.get_telegram_health", mock_get_telegram_health)
        monkeypatch.setattr("app.services.workspace_layout_service.get_user_workspace_layout", mock_get_user_workspace_layout)

        # Call the function under test
        result = get_workspace_data(user_id=1)

        # Verify response structure
        assert "market_snapshot" in result
        assert isinstance(result["market_snapshot"], dict)

        # List of fields that SHOULD NOT be at top level (they're inside market_snapshot)
        duplicate_fields = [
            "institutional_radar",
            "institutional_ranking",
            "historical_confidence",
            "historical_confidences",
            "operational_rules",
            "institutional_convictions",
            "institutional_conviction",
            "institutional_priorities",
            "institutional_priority",
            "final_decisions",
            "final_decision",
            "institutional_consistency",
        ]

        for field in duplicate_fields:
            # Either the field doesn't exist at top level, or if it does, it should be
            # a reference to the same object inside market_snapshot
            if field in result:
                # If it exists at top level, it MUST be the exact same object reference
                # as inside market_snapshot (not a duplicate copy)
                # P2' mandates these are REMOVED from top level
                pytest.fail(f"P2' VIOLATION: '{field}' found at top level - should be removed, only in market_snapshot")

        # Verify market_snapshot contains the authoritative data
        ms = result["market_snapshot"]
        for field in duplicate_fields:
            assert field in ms, f"market_snapshot missing required field: {field}"

    def test_market_snapshot_is_single_source_of_truth(self, monkeypatch):
        """All institutional data should come from market_snapshot only."""
        mock_snapshot = {
            "schema_version": 1,
            "generated_at": 1234567890.0,
            "source": "engine_v36",
            "stale": False,
            "stats": {"total_signals": 3, "bullish": 2, "bearish": 1},
            "data_status": {},
            "market_pulse": {},
            "auditor": {},
            "signals": [
                {"ticker": "VALE3", "symbol": "VALE3", "score": 75, "signal": "compra",
                 "master_verdict": "COMPRA", "rsi": 60, "price": 60.0, "volume": 500000,
                 "change_pct": 1.0, "support": 58.0, "resistance": 62.0}
            ],
            "ai_tools": {},
        }

        def mock_get_snapshot():
            return mock_snapshot

        def mock_get_snapshot_info():
            return {"timestamp": 1234567890.0, "signals": 3, "last_good_signals": 3,
                    "last_good_timestamp": 1234567890.0, "last_good_snapshot": {},
                    "snapshot_runtime": {"status": "FRESH"}}

        mocks = {
            "app.services.workspace_service.get_snapshot": mock_get_snapshot,
            "app.services.workspace_service.get_snapshot_info": mock_get_snapshot_info,
            "app.services.workspace_service.get_metrics_snapshot": lambda: {},
            "app.services.workspace_service.get_public_bootstrap": lambda: {"brand": {}},
            "app.services.workspace_service.get_layout": lambda: {"tabs": []},
            "app.services.workspace_service.get_ranking": lambda: [],
            "app.services.workspace_service.get_posts": lambda limit=10: [],
            "app.services.workspace_service.persist_ai_alert_history": lambda x: x,
            "app.services.workspace_service.get_help_center_blueprint": lambda: {},
            "app.services.workspace_service.get_media_status": lambda: {},
            "app.services.workspace_service.get_push_status": lambda: {},
            "app.api.routes_system.observability_dashboard": lambda: {"snapshot_runtime": {"status": "FRESH"},
                                                                       "go_live": {"go_live_ready": True}},
            "app.telegram.telegram_alert_engine.get_telegram_alert_history": lambda limit=30: [],
            "app.telegram.telegram_alert_engine.get_telegram_health": lambda: {},
            "app.services.workspace_layout_service.get_user_workspace_layout": lambda uid: {"tabs": [], "pinned_ticker": "PETR4"},
        }

        for target, fn in mocks.items():
            monkeypatch.setattr(target, fn)

        result = get_workspace_data(user_id=1)

        # Verify market_snapshot has all institutional data
        ms = result["market_snapshot"]
        required_ms_fields = [
            "institutional_radar", "institutional_ranking",
            "historical_confidence", "historical_confidences",
            "operational_rules",
            "institutional_convictions", "institutional_conviction",
            "institutional_priorities", "institutional_priority",
            "final_decisions", "final_decision",
            "institutional_consistency",
            "go_live_ready", "go_live",
            "institutional_consistency_score", "contract_coverage",
            "institutional_certified", "certification_timestamp",
            "certification_reasons",
        ]

        for field in required_ms_fields:
            assert field in ms, f"market_snapshot missing {field}"

        # Verify response size is reasonable (not bloated with duplicates)
        # The full payload with duplicates used to be much larger
        import json
        response_size = len(json.dumps(result, default=str))
        assert response_size < 50000, f"Response too large ({response_size} bytes) - likely has duplicates"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])