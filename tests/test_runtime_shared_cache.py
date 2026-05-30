import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.cache.signal_cache_layer import SignalCacheLayer
from app.cache.snapshot_cache import SnapshotCache


class RuntimeSharedCacheTests(unittest.TestCase):
    def test_signal_cache_is_shared_through_runtime_file(self):
        with TemporaryDirectory() as tmp:
            cache_file = os.path.join(tmp, "signals.json")
            with patch.dict(os.environ, {"SIGNAL_CACHE_FILE": cache_file}):
                writer = SignalCacheLayer()
                reader = SignalCacheLayer()

                writer.update([{"ticker": "PETR4", "score": 88.0}])
                shared = reader.get()

        self.assertEqual(len(shared), 1)
        self.assertEqual(shared[0]["ticker"], "PETR4")

    def test_snapshot_cache_is_shared_through_runtime_file(self):
        with TemporaryDirectory() as tmp:
            cache_file = os.path.join(tmp, "snapshot.json")
            with patch.dict(os.environ, {"SNAPSHOT_CACHE_FILE": cache_file}):
                writer = SnapshotCache()
                reader = SnapshotCache()

                writer.update(
                    {
                        "signals": [{"ticker": "VALE3", "score": 91.0}],
                        "source": "signal_cache",
                        "stale": False,
                    }
                )
                shared_payload = reader.get()
                shared_info = reader.info()
                shared_last_good = reader.get_last_good()

        self.assertEqual(shared_payload["signals"][0]["ticker"], "VALE3")
        self.assertEqual(shared_info["signals"], 1)
        self.assertEqual(shared_last_good["signals"][0]["ticker"], "VALE3")


if __name__ == "__main__":
    unittest.main()
