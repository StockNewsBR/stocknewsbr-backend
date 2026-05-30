import logging
import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger("stocknewsbr.cache.signal_layer")

MAX_SIGNALS = 2000


class SignalCacheLayer:
    def __init__(self):
        self._signals: List[Dict] = []
        self._timestamp: float = 0.0
        self._disk_mtime: float = 0.0
        self._lock = threading.RLock()
        self._storage_path = Path(os.getenv("SIGNAL_CACHE_FILE", "runtime/cache/signals.json"))

    def _ensure_storage_dir(self):
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

    def _write_to_disk(self):
        try:
            self._ensure_storage_dir()
            payload = {
                "timestamp": self._timestamp,
                "signals": list(self._signals[:MAX_SIGNALS]),
            }
            temp_path = self._storage_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_path.replace(self._storage_path)
            self._disk_mtime = self._storage_path.stat().st_mtime
        except Exception as exc:
            logger.exception("Signal cache persist error: %s", exc)

    def _load_from_disk_if_needed(self):
        try:
            if not self._storage_path.exists():
                return

            file_mtime = self._storage_path.stat().st_mtime
            if file_mtime <= self._disk_mtime and self._signals:
                return

            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
            signals = payload.get("signals")
            timestamp = payload.get("timestamp")

            if not isinstance(signals, list):
                signals = []
            if len(signals) > MAX_SIGNALS:
                signals = signals[:MAX_SIGNALS]

            with self._lock:
                self._signals = [item for item in signals if isinstance(item, dict)]
                self._timestamp = float(timestamp or 0.0)
                self._disk_mtime = file_mtime
        except Exception as exc:
            logger.exception("Signal cache load error: %s", exc)

    def update(self, signals: List[Dict]):
        if not signals:
            return

        try:
            now = time.time()

            if len(signals) > MAX_SIGNALS:
                signals = signals[:MAX_SIGNALS]

            with self._lock:
                self._signals = list(signals)
                self._timestamp = now
                self._write_to_disk()

        except Exception as exc:
            logger.exception("Signal cache update error: %s", exc)

    def get(self) -> List[Dict]:
        try:
            self._load_from_disk_if_needed()
            with self._lock:
                return list(self._signals)
        except Exception:
            return []

    def get_top(self, limit: int = 50) -> List[Dict]:
        try:
            self._load_from_disk_if_needed()
            with self._lock:
                return list(self._signals[:limit])
        except Exception:
            return []

    def age(self):
        self._load_from_disk_if_needed()
        ts = self._timestamp

        if ts == 0:
            return None

        return int(time.time() - ts)

    def size(self):
        try:
            self._load_from_disk_if_needed()
            with self._lock:
                return len(self._signals)
        except Exception:
            return 0

    def clear(self):
        with self._lock:
            self._signals = []
            self._timestamp = 0
            self._disk_mtime = 0.0
        try:
            if self._storage_path.exists():
                self._storage_path.unlink()
        except Exception as exc:
            logger.exception("Signal cache clear error: %s", exc)


signal_cache_layer = SignalCacheLayer()


def update_signal_cache(signals):
    signal_cache_layer.update(signals)


def get_signal_cache():
    return signal_cache_layer.get()


def get_top_signals(limit=50):
    return signal_cache_layer.get_top(limit)
