"""B7 Critical Router Startup Test

Tests that:
1. Broken critical router blocks startup (RuntimeError raised)
2. Optional (non-critical) router failure degrades observably (warning logged, startup continues)
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI

from main import _safe_import_router, _include_routers, ROUTER_SPECS, app


class TestB7CriticalRouterStartup:
    """B7: Router bootstrap - critical vs optional failure handling."""

    def test_critical_router_failure_blocks_startup(self):
        """Critical router import failure raises RuntimeError."""
        # Find a critical router
        critical_specs = [s for s in ROUTER_SPECS if s[2] is True]
        assert critical_specs, "Should have critical routers"

        module_path, attribute, critical = critical_specs[0]

        # Mock importlib to simulate failure
        with patch("importlib.import_module", side_effect=ImportError("Simulated failure")):
            with pytest.raises(RuntimeError) as exc_info:
                _safe_import_router(module_path, attribute, critical=True)

            assert "Critical router" in str(exc_info.value)
            assert module_path in str(exc_info.value)

    def test_optional_router_failure_returns_none_logs_warning(self, caplog):
        """Optional router import failure returns None and logs warning."""
        optional_specs = [s for s in ROUTER_SPECS if s[2] is False]
        assert optional_specs, "Should have optional routers"

        module_path, attribute, critical = optional_specs[0]

        with patch("importlib.import_module", side_effect=ImportError("Simulated failure")):
            result = _safe_import_router(module_path, attribute, critical=False)

        assert result is None

        # Check warning was logged
        warning_logs = [r for r in caplog.records if r.levelname == "WARNING"]
        assert any("Skipping non-critical router" in r.message for r in warning_logs)

    def test_router_spec_structure(self):
        """ROUTER_SPECS are tuples of (module, attribute, critical_bool)."""
        for spec in ROUTER_SPECS:
            assert len(spec) == 3, f"Spec {spec} should have 3 elements"
            module_path, attribute, critical = spec
            assert isinstance(module_path, str)
            assert isinstance(attribute, str)
            assert isinstance(critical, bool)

    def test_critical_routers_list(self):
        """Verify expected critical routers are marked as such."""
        critical_modules = [s[0] for s in ROUTER_SPECS if s[2]]

        expected_critical = [
            "app.auth",
            "app.api.routes_system",
            "app.api.routes_snapshot",
            "app.api.routes_signals",
            "app.api.routes_internal",
            "app.api.routes_radar",
            "app.api.routes_feed",
            "app.api.routes_push",
            "app.api.routes_news",
            "app.api.routes_app_workspace",
            "app.services.ranking",
            "app.system.stream_router",
        ]

        for expected in expected_critical:
            assert expected in critical_modules, f"Expected critical router {expected} not found"

    def test_optional_routers_list(self):
        """Optional routers should not block startup."""
        optional_modules = [s[0] for s in ROUTER_SPECS if not s[2]]

        # These should be optional (not critical)
        expected_optional = [
            "app.api.routes_opportunity",
            "app.api.routes_public_meta",
            "app.api.routes_public_market",
            "app.api.routes_public_market_live",
            "app.api.routes_paper_trading",
            "app.api.routes_performance_intelligence",
            "app.api.routes_explainability",
            "app.api.api_market_routes",
            "app.api.market_routes",
            "app.api.routes_heatmap",
            "app.api.routes_narrative",
            "app.api.routes_market_bar",
            "app.api.routes_activity",
            "app.api.routes_likes",
            "app.api.routes_moderation",
            "app.api.routes_moderation_admin",
            "app.api.routes_media",
            "app.api.routes_poll",
            "app.api.routes_sentiment",
            "app.api.routes_social",
            "app.api.routes_chat",
            "app.api.stripe_webhook",
            "app.api.routes_ticker",
            "app.web.routes_chart",
            "app.web.routes_dashboard",
            "app.web.routes_market_pulse",
            "app.web.routes_opportunities",
            "app.web.routes_radar",
            "app.web.routes_search",
            "app.web.routes_terminal",
            "app.web.routes_top_movers",
            "app.web.routes_watchlist",
            "app.web.routes_workspace",
            "app.web.routes_site",
        ]

        for expected in expected_optional:
            assert expected in optional_modules, f"Expected optional router {expected} not found"

    def test_include_routers_skips_failed_optional(self, caplog):
        """_include_routers should continue on optional router failures."""
        with patch("importlib.import_module") as mock_import:
            # Make first router succeed, second (optional) fail, third succeed
            mock_router1 = MagicMock()
            mock_router2_fail = MagicMock(side_effect=ImportError("Fail"))
            mock_router3 = MagicMock()

            def side_effect(module_path):
                if "routes_opportunity" in module_path:
                    raise ImportError("Fail")
                return MagicMock(router=MagicMock())

            mock_import.side_effect = side_effect

            test_app = FastAPI()
            _include_routers(test_app)

            # Should have logged warning for optional failure
            warning_logs = [r for r in caplog.records if r.levelname == "WARNING"]
            assert any("Skipping non-critical router" in r.message for r in warning_logs)

    def test_include_routers_stops_on_critical_failure(self):
        """_include_routers should propagate RuntimeError on critical failure."""
        with patch("importlib.import_module", side_effect=ImportError("Critical fail")):
            test_app = FastAPI()
            with pytest.raises(RuntimeError):
                _include_routers(test_app)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])