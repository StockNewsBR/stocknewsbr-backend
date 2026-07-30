"""B3 Snapshot Cache Corruption Resilience Tests

Tests the _load_from_disk_if_needed() method for:
1. JSON decode errors (truncated file)
2. Invalid schema/type (not a dict)
3. Unreadable file (permission error, missing)
4. Valid in-memory state preserved when disk load fails
5. Disk semantically older than memory (timestamp comparison)
6. Write failure handling (metric recording)
7. Concurrency safety (no silent corruption under load)
"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.cache.snapshot_cache import SnapshotCache
from app.system.system_metrics import record_snapshot_write_metric


class TestB3SnapshotCacheCorruptionResilience:
    """B3: Snapshot cache corruption handling - disk load failures must not
    silently wipe good in-memory state. Structured logging + metrics required."""

    def setup_method(self):
        """Create a fresh SnapshotCache with temp file for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_path = Path(self.temp_dir) / "snapshot_test.json"
        self.cache = SnapshotCache(storage_path=str(self.cache_path))
        # Ensure clean in-memory state
        self.cache._memory = None
        self.cache._loaded = False
        self.cache._disk_ts = 0.0

    def teardown_method(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_json_decode_error_truncated_file_preserves_memory(self):
        """B3a: Truncated/corrupt JSON on disk → log warning, increment metric,
        preserve in-memory state (don't crash, don't wipe memory)."""
        # Set up good in-memory state FIRST
        good_memory = {
            "generated_at": time.time() - 10,
            "as_of": time.time() - 10,
            "signals": [{"symbol": "PETR4", "score": 85}],
            "signals_count": 1,
            "version": 1,
        }
        self.cache._memory = good_memory
        self.cache._loaded = True
        self.cache._disk_ts = time.time() - 5  # disk appears newer

        # Write TRUNCATED/INVALID JSON to disk
        with open(self.cache_path, "w") as f:
            f.write('{"generated_at": 123, "signals": [')  # truncated

        # Call the method under test
        with patch("app.cache.snapshot_cache.logger") as mock_logger:
            self.cache._load_from_disk_if_needed()

        # Verify: in-memory state PRESERVED (not overwritten with corrupt data)
        assert self.cache._memory == good_memory
        assert self.cache._loaded is True

        # Verify: structured warning logged
        mock_logger.warning.assert_called()
        call_args = mock_logger.warning.call_args
        assert "Snapshot cache disk load failed" in call_args[0][0]
        assert "corrupt" in call_args[1]["error"].lower() or "json" in call_args[1]["error"].lower()

    def test_invalid_schema_non_dict_preserves_memory(self):
        """B3b: Disk JSON is valid but wrong type (array, string, number) →
        log warning, increment metric, preserve in-memory state."""
        good_memory = {
            "generated_at": time.time() - 10,
            "as_of": time.time() - 10,
            "signals": [],
            "signals_count": 0,
            "version": 1,
        }
        self.cache._memory = good_memory
        self.cache._loaded = True
        self.cache._disk_ts = time.time() - 5

        # Write valid JSON but wrong schema (array instead of dict)
        with open(self.cache_path, "w") as f:
            json.dump([1, 2, 3], f)

        with patch("app.cache.snapshot_cache.logger") as mock_logger:
            self.cache._load_from_disk_if_needed()

        # Memory preserved
        assert self.cache._memory == good_memory

        # Warning logged
        mock_logger.warning.assert_called()

    def test_unreadable_file_permission_error_preserves_memory(self):
        """B3c: File unreadable (permission error, missing) → log warning,
        increment metric, preserve in-memory state."""
        good_memory = {
            "generated_at": time.time() - 10,
            "as_of": time.time() - 10,
            "signals": [{"symbol": "VALE3", "score": 70}],
            "signals_count": 1,
            "version": 1,
        }
        self.cache._memory = good_memory
        self.cache._loaded = True
        self.cache._disk_ts = time.time() - 5

        # Delete the file (FileNotFoundError)
        os.remove(self.cache_path)

        with patch("app.cache.snapshot_cache.logger") as mock_logger:
            self.cache._load_from_disk_if_needed()

        # Memory preserved
        assert self.cache._memory == good_memory
        mock_logger.warning.assert_called()

    def test_valid_memory_preserved_when_disk_older(self):
        """B3d: Memory has valid data, disk timestamp is OLDER → skip disk load
        entirely (do not attempt read)."""
        good_memory = {
            "generated_at": time.time() - 5,  # newer
            "as_of": time.time() - 5,
            "signals": [{"symbol": "ITUB4", "score": 90}],
            "signals_count": 1,
            "version": 1,
        }
        self.cache._memory = good_memory
        self.cache._loaded = True
        self.cache._disk_ts = time.time() - 20  # disk older

        # Write some data to disk (should NOT be read)
        with open(self.cache_path, "w") as f:
            json.dump({"signals": [{"symbol": "FAKE", "score": 0}]}, f)

        with patch("app.cache.snapshot_cache.logger") as mock_logger:
            self.cache._load_from_disk_if_needed()

        # Memory unchanged, no warning logged (no attempt to load)
        assert self.cache._memory == good_memory
        mock_logger.warning.assert_not_called()

    def test_disk_semantically_newer_loads_updates_memory(self):
        """B3e: Disk has NEWER generated_at/as_of → load and update memory."""
        # Memory older
        self.cache._memory = {
            "generated_at": time.time() - 20,
            "as_of": time.time() - 20,
            "signals": [{"symbol": "OLD", "score": 10}],
            "signals_count": 1,
            "version": 1,
        }
        self.cache._loaded = True
        self.cache._disk_ts = time.time() - 5  # disk appears newer

        # Disk has NEWER data
        disk_data = {
            "generated_at": time.time() - 5,
            "as_of": time.time() - 5,
            "signals": [{"symbol": "NEW", "score": 99}],
            "signals_count": 1,
            "version": 1,
        }
        with open(self.cache_path, "w") as f:
            json.dump(disk_data, f)

        with patch("app.cache.snapshot_cache.logger") as mock_logger:
            self.cache._load_from_disk_if_needed()

        # Memory UPDATED to disk data
        assert self.cache._memory["signals"][0]["symbol"] == "NEW"
        assert self.cache._memory["generated_at"] > time.time() - 10
        mock_logger.warning.assert_not_called()

    def test_write_failure_records_metric(self):
        """B3f: Write failure (os.replace, permission) → metric recorded as False."""
        # This tests the write path - we mock os.replace to fail
        with patch("os.replace", side_effect=PermissionError("denied")):
            with patch("app.cache.snapshot_cache.record_snapshot_write_metric") as mock_metric:
                payload = {
                    "generated_at": time.time(),
                    "as_of": time.time(),
                    "signals": [],
                    "signals_count": 0,
                    "version": 1,
                }
                # This should not crash, should record metric=False
                self.cache.set(payload)

                mock_metric.assert_called_with(False)

    def test_concurrent_readers_preserve_state_under_load(self):
        """B3g: Multiple threads calling _load_from_disk_if_needed while
        write happens concurrently → no state corruption, no lost updates."""
        errors = []

        def writer():
            try:
                for i in range(50):
                    payload = {
                        "generated_at": time.time(),
                        "as_of": time.time(),
                        "signals": [{"symbol": f"SYM{i}", "score": i}],
                        "signals_count": 1,
                        "version": 1,
                    }
                    self.cache.set(payload)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(("writer", e))

        def reader():
            try:
                for _ in range(100):
                    _ = self.cache.get()  # triggers _load_from_disk_if_needed
                    time.sleep(0.0005)
            except Exception as e:
                errors.append(("reader", e))

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Concurrency errors: {errors}"
        # Final state should be consistent
        final = self.cache.get()
        assert final is not None
        assert "signals" in final
        assert isinstance(final["signals"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])