import logging
import os
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Dict, List

from app.core.atomic_io import read_json_file_consistent, write_json_file_atomic

logger = logging.getLogger("stocknewsbr.cache.signal_layer")

MAX_SIGNALS = 2000
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _project_runtime_path(env_name: str, default_relative: str) -> Path:
    configured = os.getenv(env_name)
    if configured:
        configured_path = Path(configured)
        return (
            configured_path
            if configured_path.is_absolute()
            else _PROJECT_ROOT / configured_path
        )
    return _PROJECT_ROOT / default_relative


class SignalCacheLayer:
    def __init__(self):
        self._signals: List[Dict] = []
        self._timestamp: float = 0.0
        self._disk_mtime: float = 0.0
        self._lock = threading.RLock()
        self._disk_write_lock = threading.Lock()
        self._write_epoch = 0
        self._storage_path = _project_runtime_path(
            "SIGNAL_CACHE_FILE", "runtime/cache/signals.json"
        )

    def _ensure_storage_dir(self):
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

    def _write_to_disk(
        self,
        *,
        expected_timestamp: float | None = None,
        expected_epoch: int | None = None,
    ):
        try:
            self._ensure_storage_dir()
            with self._disk_write_lock:
                with self._lock:
                    if (
                        expected_timestamp is not None
                        and self._timestamp != expected_timestamp
                    ):
                        return
                    if (
                        expected_epoch is not None
                        and self._write_epoch != expected_epoch
                    ):
                        return
                    signals_ref = self._signals[:MAX_SIGNALS]
                    ts = self._timestamp

                payload = {
                    "timestamp": ts,
                    "signals": deepcopy(signals_ref),
                }
                write_json_file_atomic(self._storage_path, payload, ensure_ascii=False)
                with self._lock:
                    if self._timestamp == float(payload.get("timestamp") or 0.0):
                        self._disk_mtime = self._storage_path.stat().st_mtime
        except Exception as exc:
            logger.exception("Signal cache persist error: %s", exc)

    def _load_from_disk_if_needed(self):
        try:
            if not self._storage_path.exists():
                return

            file_mtime = self._storage_path.stat().st_mtime
            if file_mtime <= self._disk_mtime:
                return

            payload, stable_mtime, _stable_size = read_json_file_consistent(
                self._storage_path,
                lambda: {},
            )
            if not isinstance(payload, dict):
                with self._lock:
                    self._signals = []
                    self._timestamp = 0.0
                    self._disk_mtime = stable_mtime or file_mtime
                return

            signals = payload.get("signals")
            timestamp = payload.get("timestamp")

            if not isinstance(signals, list):
                signals = []
            if len(signals) > MAX_SIGNALS:
                signals = signals[:MAX_SIGNALS]

            new_signals = [deepcopy(item) for item in signals if isinstance(item, dict)]

            with self._lock:
                self._signals = new_signals
                self._timestamp = float(timestamp or 0.0)
                self._disk_mtime = stable_mtime or file_mtime
        except Exception as exc:
            logger.exception("Signal cache load error: %s", exc)

    def update(self, signals: List[Dict]):
        if not signals:
            return

        try:
            now = time.time()

            if len(signals) > MAX_SIGNALS:
                signals = signals[:MAX_SIGNALS]

            new_signals = [deepcopy(item) for item in signals if isinstance(item, dict)]

            with self._lock:
                self._signals = new_signals
                self._timestamp = now
                write_epoch = self._write_epoch

            self._write_to_disk(expected_timestamp=now, expected_epoch=write_epoch)

        except Exception as exc:
            logger.exception("Signal cache update error: %s", exc)

    def get(self) -> List[Dict]:
        try:
            self._load_from_disk_if_needed()
            with self._lock:
                signals_ref = self._signals
            return deepcopy(signals_ref)
        except Exception:
            return []

    def get_top(self, limit: int = 50) -> List[Dict]:
        try:
            self._load_from_disk_if_needed()
            with self._lock:
                signals_ref = self._signals[:limit]
            return deepcopy(signals_ref)
        except Exception:
            return []

    def age(self):
        self._load_from_disk_if_needed()
        with self._lock:
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
        with self._disk_write_lock:
            with self._lock:
                self._write_epoch += 1
                self._signals = []
                self._timestamp = 0
            try:
                self._ensure_storage_dir()
                write_json_file_atomic(
                    self._storage_path,
                    {"timestamp": 0.0, "signals": []},
                    ensure_ascii=False,
                )
                with self._lock:
                    self._disk_mtime = self._storage_path.stat().st_mtime
            except Exception as exc:
                logger.exception("Signal cache clear error: %s", exc)
                # Mission 31F: falha ao persistir o clear não pode recarregar
                # estado antigo do disco; marca o mtime atual como consumido.
                with self._lock:
                    try:
                        self._disk_mtime = self._storage_path.stat().st_mtime
                    except Exception:
                        pass


signal_cache_layer = SignalCacheLayer()


def update_signal_cache(signals):
    signal_cache_layer.update(signals)


def get_signal_cache():
    return signal_cache_layer.get()


def get_top_signals(limit=50):
    return signal_cache_layer.get_top(limit)
