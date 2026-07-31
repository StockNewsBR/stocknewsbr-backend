"""P2' Workspace canonical-source tests.

The confirmed P2' finding is DIVERGENCE, not duplication: the workspace response
carried institutional data twice -- once recomputed per request from the (already
truncated) signal list, and once resolved from the engine-cached snapshot -- so the two
representations could hold different values for the same field name.

The fix is a single canonical source (market_snapshot) with the historical top-level
fields kept as derived projections of it. Deleting the top-level fields is NOT the fix:
they are the literal HTTP response body of /web/workspace/data and /app/workspace/data,
and apps/web/lib/types.ts still declares them on WorkspaceData.

These tests pin the whole contract: presence, equality, single-source-under-conflict,
historical consumers, and mutation isolation between the two representations.
"""

import pytest

from app.services.workspace_service import _CANONICAL_COMPAT_FIELDS, get_workspace_data


def _install_workspace_mocks(monkeypatch, snapshot, *, observability=None):
    """Patch every external dependency of get_workspace_data.

    The bootstrap mock must be complete: workspace_service reads brand/pricing/
    launch_roadmap/ai_modules/social_features by direct subscript, so a partial mock
    raises KeyError before the function returns and masks whatever the test meant to
    assert.
    """
    bootstrap = {
        "brand": {"name": "StockNewsBR"},
        "pricing": {"plan": "premium"},
        "launch_roadmap": [],
        "ai_modules": [],
        "social_features": [],
    }
    observability = observability or {
        "snapshot_runtime": {"status": "FRESH"},
        "go_live": {
            "go_live_ready": True,
            "institutional_consistency_score": 80,
            "contract_coverage": {"coverage_pct": 100.0},
            "institutional_certified": True,
            "certification_timestamp": 1234567890.0,
            "certification_reasons": ["ok"],
        },
    }
    snapshot_info = {
        "timestamp": 1234567890.0,
        "signals": 5,
        "last_good_signals": 5,
        "last_good_timestamp": 1234567890.0,
        "last_good_snapshot": {"signals": 5, "timestamp": 1234567890.0},
        "snapshot_runtime": {"status": "FRESH"},
    }

    mocks = {
        "app.services.workspace_service.get_snapshot": lambda: snapshot,
        "app.services.workspace_service.get_snapshot_info": lambda: snapshot_info,
        # workspace_service reads these by direct subscript too.
        "app.services.workspace_service.get_metrics_snapshot": lambda: {
            "engine_cycles": 0,
            "signals_generated": 0,
            "assets_scanned": 0,
            "cache_age": 0,
            "http_requests": 0,
            "ws_connections": 0,
            "chat_messages": 0,
        },
        "app.services.workspace_service.get_public_bootstrap": lambda: bootstrap,
        "app.services.workspace_service.get_layout": lambda: {"tabs": []},
        "app.services.workspace_service.get_ranking": lambda: [],
        "app.services.workspace_service.get_posts": lambda limit=10: [],
        "app.services.workspace_service.persist_ai_alert_history": lambda x: x,
        "app.services.workspace_service.get_help_center_blueprint": lambda: {},
        "app.services.workspace_service.get_media_status": lambda: {},
        "app.services.workspace_service.get_push_status": lambda: {},
        "app.api.routes_system.observability_dashboard": lambda: observability,
        "app.telegram.telegram_alert_engine.get_telegram_alert_history": lambda limit=30: [],
        "app.telegram.telegram_alert_engine.get_telegram_health": lambda: {},
        "app.services.workspace_layout_service.get_user_workspace_layout": lambda uid: {
            "tabs": [],
            "pinned_ticker": "PETR4",
        },
    }
    for target, fn in mocks.items():
        monkeypatch.setattr(target, fn)


def _snapshot(**overrides):
    base = {
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
                "ticker": "PETR4", "symbol": "PETR4", "score": 85, "signal": "compra",
                "master_verdict": "COMPRA", "rsi": 65, "price": 40.50, "volume": 1000000,
                "change_pct": 2.5, "support": 39.0, "resistance": 42.0,
            }
        ],
        "ai_tools": {"institutional_conviction": [], "institutional_priority": []},
    }
    base.update(overrides)
    return base


class TestP2PrimeCanonicalSource:
    def test_compatibility_fields_are_present_at_top_level(self, monkeypatch):
        """1. Historical consumers still find the fields they read."""
        _install_workspace_mocks(monkeypatch, _snapshot())
        result = get_workspace_data(user_id=1)

        missing = [f for f in _CANONICAL_COMPAT_FIELDS if f not in result]
        assert missing == [], f"top-level compatibility fields missing: {missing}"

    def test_top_level_equals_market_snapshot(self, monkeypatch):
        """2. Each projection equals its canonical counterpart -- no divergence."""
        _install_workspace_mocks(monkeypatch, _snapshot())
        result = get_workspace_data(user_id=1)
        market_snapshot = result["market_snapshot"]

        for field in _CANONICAL_COMPAT_FIELDS:
            assert field in market_snapshot, f"market_snapshot missing canonical field {field}"
            assert result[field] == market_snapshot[field], f"divergence on {field}"

    def test_conflicting_snapshot_yields_one_value_not_two(self, monkeypatch):
        """3. A deliberately conflicting snapshot must not produce two sources.

        The engine-cached blocks below disagree with anything the request path would
        recompute from `signals`. Before the fix the top level showed the recomputed
        value while market_snapshot showed the cached one; now both must show the
        canonical (cached) value.
        """
        conflicting = _snapshot(
            institutional_radar=[{"ticker": "CACHED_ONLY", "score": 99.0}],
            institutional_ranking=[{"ticker": "CACHED_RANK", "score": 98.0}],
            final_decisions=[{"ticker": "CACHED_DECISION", "score": 97.0}],
            operational_rules={"source": "engine_cache"},
            institutional_consistency={"source": "engine_cache"},
        )
        _install_workspace_mocks(monkeypatch, conflicting)
        result = get_workspace_data(user_id=1)
        market_snapshot = result["market_snapshot"]

        # The canonical value wins, and the top level mirrors it exactly.
        assert [row["ticker"] for row in market_snapshot["institutional_radar"]] == ["CACHED_ONLY"]
        for field in ("institutional_radar", "institutional_ranking", "final_decisions",
                      "operational_rules", "institutional_consistency"):
            assert result[field] == market_snapshot[field], f"conflicting snapshot diverged on {field}"

        # And PETR4 (what a request-time recomputation would have produced) never leaks in.
        assert "PETR4" not in [row.get("ticker") for row in result["institutional_radar"]]

    def test_go_live_agrees_across_all_representations(self, monkeypatch):
        """4. Historical consumers: flat, status.* and market_snapshot.* must agree."""
        _install_workspace_mocks(monkeypatch, _snapshot())
        result = get_workspace_data(user_id=1)

        assert result["go_live_ready"] is True
        assert result["status"]["go_live_ready"] == result["go_live_ready"]
        assert result["market_snapshot"]["go_live_ready"] == result["go_live_ready"]
        assert result["contract_coverage"] == result["market_snapshot"]["contract_coverage"]

    def test_mutating_one_representation_does_not_affect_the_other(self, monkeypatch):
        """5. Projections are equal but not the same container."""
        _install_workspace_mocks(monkeypatch, _snapshot())
        result = get_workspace_data(user_id=1)
        market_snapshot = result["market_snapshot"]

        mutated = []
        for field in _CANONICAL_COMPAT_FIELDS:
            value = result[field]
            if isinstance(value, list):
                value.append({"ticker": "INJECTED"})
                mutated.append(field)
            elif isinstance(value, dict):
                value["__injected__"] = True
                mutated.append(field)

        assert mutated, "expected at least one mutable projection to exercise"
        for field in mutated:
            canonical = market_snapshot[field]
            if isinstance(canonical, list):
                assert {"ticker": "INJECTED"} not in canonical, f"{field} leaked a mutation"
            else:
                assert "__injected__" not in canonical, f"{field} leaked a mutation"

    def test_single_projection_site_no_duplicate_dict_keys(self, monkeypatch):
        """Regression: the fields were once written twice in the same dict literal.

        A repeated key in a dict literal silently keeps the last write, which is what hid
        the incomplete removal in 4e20ee24. Projecting from one place makes that
        impossible, and this asserts the projection is what actually reached the caller.
        """
        _install_workspace_mocks(monkeypatch, _snapshot())
        result = get_workspace_data(user_id=1)
        market_snapshot = result["market_snapshot"]

        for field in ("institutional_conviction", "institutional_priority",
                      "final_decision", "institutional_consistency"):
            assert result[field] == market_snapshot[field]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
