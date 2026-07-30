"""B8 Signal Engine Deletion Verification Test

Verifies that app/engine/signal_engine.py has been fully removed
and no dynamic imports or references remain.
"""

import ast
import os
from pathlib import Path

import pytest


class TestB8SignalEngineDeleted:
    """B8: signal_engine.py deleted - verify no imports remain."""

    def test_signal_engine_file_deleted(self):
        """signal_engine.py should not exist."""
        path = Path("/home/dcima/stocknewsbr-backend/app/engine/signal_engine.py")
        assert not path.exists(), "signal_engine.py should have been deleted"

    def test_no_static_imports_of_signal_engine(self):
        """No .py files should statically import from signal_engine."""
        project_root = Path("/home/dcima/stocknewsbr-backend")
        violations = []

        for py_file in project_root.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            if "test_" in py_file.name and "test_mission" not in py_file.name:
                # Skip root test_*.py files (they're untracked scratch files)
                continue

            try:
                content = py_file.read_text()
                if "from app.engine.signal_engine import" in content or \
                   "import app.engine.signal_engine" in content or \
                   "from app.engine import signal_engine" in content:
                    violations.append(str(py_file.relative_to(project_root)))
            except Exception:
                pass

        assert not violations, f"Static imports of signal_engine found in: {violations}"

    def test_no_dynamic_imports_of_signal_engine(self):
        """No importlib/__import__/getattr dynamic imports of signal_engine."""
        project_root = Path("/home/dcima/stocknewsbr-backend")
        violations = []

        for py_file in project_root.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            if "test_" in py_file.name and "test_mission" not in py_file.name:
                continue

            try:
                content = py_file.read_text()
                # Check for dynamic import patterns
                patterns = [
                    'import_module("app.engine.signal_engine',
                    "import_module('app.engine.signal_engine",
                    '__import__("app.engine.signal_engine',
                    "__import__('app.engine.signal_engine",
                    'getattr(.*signal_engine',
                    'importlib.import_module.*signal_engine',
                ]
                for pattern in patterns:
                    if pattern in content:
                        violations.append(str(py_file.relative_to(project_root)))
                        break
            except Exception:
                pass

        assert not violations, f"Dynamic imports of signal_engine found in: {violations}"

    def test_no_entry_points_reference_signal_engine(self):
        """setup.cfg/pyproject.toml entry points should not reference signal_engine."""
        project_root = Path("/home/dcima/stocknewsbr-backend")

        for config_file in ["setup.cfg", "pyproject.toml", "setup.py"]:
            path = project_root / config_file
            if path.exists():
                content = path.read_text()
                assert "signal_engine" not in content, f"{config_file} references signal_engine"

    def test_no_scripts_reference_signal_engine(self):
        """No scripts in scripts/ or bin/ should import signal_engine."""
        project_root = Path("/home/dcima/stocknewsbr-backend")

        for script_dir in ["scripts", "bin", "tools"]:
            script_path = project_root / script_dir
            if script_path.exists():
                for script in script_path.rglob("*.py"):
                    content = script.read_text()
                    assert "signal_engine" not in content, f"Script {script} references signal_engine"

    def test_related_modules_exist_and_import_correctly(self):
        """Related modules that were refactored should still exist and work."""
        # These modules should exist and import without signal_engine
        required_modules = [
            "app.engine.trend_breakout_signal_engine",
            "app.engine.chart_signal_adapter",
            "app.portfolio.backtest_engine",
            "app.web.routes_chart",
            "app.api.routes_chart",
            "app.api.routes_public_market_live",
        ]

        for module_name in required_modules:
            try:
                __import__(module_name)
            except ImportError as e:
                pytest.fail(f"Required module {module_name} failed to import: {e}")

    def test_build_chart_signal_payload_available(self):
        """build_chart_signal_payload should be available from trend_breakout_signal_engine."""
        from app.engine.trend_breakout_signal_engine import build_trend_breakout_payload
        from app.engine.chart_signal_adapter import build_chart_signal_payload

        # Both should be callable
        assert callable(build_trend_breakout_payload)
        assert callable(build_chart_signal_payload)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])