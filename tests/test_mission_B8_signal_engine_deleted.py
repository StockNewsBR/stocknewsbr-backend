"""B8 Signal Engine Deletion Verification Test

Verifies that app/engine/signal_engine.py has been fully removed
and no dynamic imports or references remain.
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Third-party trees are not ours to police, and scanning them is slow.
_EXCLUDED_PARTS = {"__pycache__", "venv", ".venv", "node_modules", ".git", "build", "dist"}


def _scan_for(needles: tuple[str, ...]) -> list[str]:
    """Return repo files containing any needle.

    This scanner must skip itself: the needles it searches for are present in its own
    source as string literals, so including it guarantees a self-match and the assertion
    can never pass -- not even once signal_engine is genuinely gone.
    """
    this_file = Path(__file__).resolve()
    violations = []

    for py_file in PROJECT_ROOT.rglob("*.py"):
        if _EXCLUDED_PARTS & set(py_file.parts):
            continue
        if py_file.resolve() == this_file:
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(needle in content for needle in needles):
            violations.append(str(py_file.relative_to(PROJECT_ROOT)))

    return violations


class TestB8SignalEngineDeleted:
    """B8: signal_engine.py deleted - verify no imports remain."""

    def test_signal_engine_file_deleted(self):
        """app/engine/signal_engine.py should not exist.

        Note this is a different file from app/ai/signal_engine.py, which 9d5b5386
        deleted. This one survived that commit and stayed tracked with zero importers.
        """
        assert not (PROJECT_ROOT / "app" / "engine" / "signal_engine.py").exists(), (
            "app/engine/signal_engine.py should have been deleted"
        )

    def test_module_is_not_importable(self):
        with pytest.raises(ModuleNotFoundError):
            __import__("app.engine.signal_engine")

    def test_replacement_adapter_still_enriches_ai_context(self):
        """Deletion is only legitimate because the behaviour was migrated first.

        1e84bab7 removed the last importer but replaced the enrichment with
        `ai_context={}`, so the module was 'unused' only because the live flow had been
        silently downgraded. This pins the migrated behaviour so the module can never be
        re-declared dead by re-introducing that downgrade.
        """
        import app.engine.chart_signal_adapter as adapter

        for name in (
            "_build_ai_context_from_snapshot",
            "_safe_ai_context",
            "_find_ai_row",
            "_metric_ai_row",
            "_snapshot_master_score_row",
            "_normalize_symbol",
        ):
            assert hasattr(adapter, name), f"adapter lost migrated helper {name}"

        source = (PROJECT_ROOT / "app" / "engine" / "chart_signal_adapter.py").read_text()
        assert "ai_context={}" not in source, "the empty-context downgrade came back"
        assert "ai_context=_safe_ai_context(symbol)" in source

    def test_no_static_imports_of_signal_engine(self):
        """No .py files should statically import from signal_engine."""
        violations = _scan_for(
            (
                "from app.engine.signal_engine import",
                "import app.engine.signal_engine",
                "from app.engine import signal_engine",
            )
        )
        assert not violations, f"Static imports of signal_engine found in: {violations}"

    def test_no_dynamic_imports_of_signal_engine(self):
        """No importlib/__import__ dynamic imports of signal_engine."""
        violations = _scan_for(
            (
                'import_module("app.engine.signal_engine',
                "import_module('app.engine.signal_engine",
                '__import__("app.engine.signal_engine',
                "__import__('app.engine.signal_engine",
            )
        )
        assert not violations, f"Dynamic imports of signal_engine found in: {violations}"

    def test_no_entry_points_reference_signal_engine(self):
        """setup.cfg/pyproject.toml entry points should not reference signal_engine."""
        project_root = PROJECT_ROOT

        for config_file in ["setup.cfg", "pyproject.toml", "setup.py"]:
            path = project_root / config_file
            if path.exists():
                content = path.read_text()
                assert "signal_engine" not in content, f"{config_file} references signal_engine"

    def test_no_scripts_reference_signal_engine(self):
        """No scripts in scripts/ or bin/ should import signal_engine."""
        project_root = PROJECT_ROOT

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