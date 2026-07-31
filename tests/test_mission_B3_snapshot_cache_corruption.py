"""B3 Snapshot Cache Corruption Resilience Tests

Tests the SnapshotCache disk load behavior for:
1. JSON decode errors (truncated file)
2. Invalid schema/type (not a dict)
3. Schema missing required envelope or legacy markers
4. Unreadable file (missing file)
5. Valid in-memory state preserved when disk load fails
6. Write failure handling (metric recording)
7. Time parsing robustness
"""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from app.cache.snapshot_cache import SnapshotCache


class TestB3SnapshotCacheCorruptionResilience:
    """B3: Snapshot cache corruption handling - disk load failures must not
    silently wipe good in-memory state. Structured logging + metrics required."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cache_path = Path(self.temp_dir) / "snapshot_test.json"
        os.environ["SNAPSHOT_CACHE_FILE"] = str(self.cache_path)
        
        self.cache = SnapshotCache()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        os.environ.pop("SNAPSHOT_CACHE_FILE", None)

    def test_json_decode_error_truncated_file_preserves_memory(self):
        # Set up good memory via update()
        good_memory = {
            "signals": [{"symbol": "PETR4", "score": 85}],
            "generated_at": time.time() - 10,
        }
        self.cache.update(good_memory)
        
        # Now corrupt the file on disk
        with open(self.cache_path, "w") as f:
            f.write('{"generated_at": 123, "signals": [')

        # Trigger load
        with patch("app.cache.snapshot_cache.logger") as mock_logger:
            result = self.cache.get()

        # Should return memory data despite corrupt disk
        assert len(result.get("signals", [])) == 1
        assert result["signals"][0]["symbol"] == "PETR4"
        
        mock_logger.warning.assert_called()
        args, kwargs = mock_logger.warning.call_args
        assert "disk load failed" in args[0].lower()
        assert "error" in kwargs.get("extra", {})

    def test_invalid_schema_non_dict_preserves_memory(self):
        good_memory = {
            "signals": [{"symbol": "VALE3", "score": 99}],
            "generated_at": time.time() - 10,
        }
        self.cache.update(good_memory)

        with open(self.cache_path, "w") as f:
            json.dump([1, 2, 3], f)

        with patch("app.cache.snapshot_cache.logger") as mock_logger:
            result = self.cache.get()

        assert len(result.get("signals", [])) == 1
        assert result["signals"][0]["symbol"] == "VALE3"
        mock_logger.warning.assert_called()

    def test_invalid_schema_missing_envelope_preserves_memory(self):
        good_memory = {
            "signals": [{"symbol": "ITUB4", "score": 50}],
            "generated_at": time.time() - 10,
        }
        self.cache.update(good_memory)

        with open(self.cache_path, "w") as f:
            json.dump({"random_key": "no_signals_or_timestamps"}, f)

        with patch("app.cache.snapshot_cache.logger") as mock_logger:
            result = self.cache.get()

        assert len(result.get("signals", [])) == 1
        assert result["signals"][0]["symbol"] == "ITUB4"
        mock_logger.warning.assert_called()

    def test_missing_file_preserves_memory(self):
        good_memory = {
            "signals": [{"symbol": "BBDC4", "score": 75}],
            "generated_at": time.time() - 10,
        }
        self.cache.update(good_memory)

        # Remove the file entirely
        os.remove(self.cache_path)

        with patch("app.cache.snapshot_cache.logger") as mock_logger:
            result = self.cache.get()

        assert len(result.get("signals", [])) == 1
        assert result["signals"][0]["symbol"] == "BBDC4"
        mock_logger.warning.assert_called()
        
    def test_timestamp_parsing_robustness(self):
        # Test the static _parse_timestamp method
        assert SnapshotCache._parse_timestamp(123456.0) == 123456.0
        assert SnapshotCache._parse_timestamp(None) == 0.0
        assert SnapshotCache._parse_timestamp("") == 0.0
        assert SnapshotCache._parse_timestamp("garbage") == 0.0
        
        iso_val = "2026-07-31T10:00:00Z"
        parsed = SnapshotCache._parse_timestamp(iso_val)
        assert parsed > 0.0

    def test_write_failure_records_metric(self):
        with patch("app.core.atomic_io.os.replace", side_effect=PermissionError("denied")):
            with patch("app.cache.snapshot_cache.record_snapshot_write_metric") as mock_metric:
                self.cache.update({"signals": [{"symbol": "MGLU3"}], "generated_at": time.time()})
                mock_metric.assert_called_with(False)

    def test_concurrent_readers_preserve_state_under_load(self):
        """B3g: Multiple threads calling get() while write happens concurrently."""
        import threading
        errors = []

        def writer():
            try:
                for i in range(10):
                    self.cache.update({
                        "signals": [{"symbol": f"SYM{i}", "score": i}],
                        "generated_at": time.time(),
                    })
                    time.sleep(0.01)
            except Exception as e:
                errors.append(("writer", e))

        def reader():
            try:
                for _ in range(20):
                    _ = self.cache.get()
                    time.sleep(0.005)
            except Exception as e:
                errors.append(("reader", e))

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors
        final = self.cache.get()
        assert final is not None

if __name__ == "__main__":
    pytest.main([__file__, "-v"])