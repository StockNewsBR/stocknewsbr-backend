"""B8 Signal Engine Deletion Verification Test

Verifies that app/engine/signal_engine.py has been fully removed.
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

class TestB8SignalEngineDeleted:
    """B8: signal_engine.py deleted."""

    def test_signal_engine_file_deleted(self):
        """app/engine/signal_engine.py should not exist."""
        assert not (PROJECT_ROOT / "app" / "engine" / "signal_engine.py").exists(), (
            "app/engine/signal_engine.py should have been deleted"
        )

if __name__ == "__main__":
    pytest.main([__file__, "-v"])