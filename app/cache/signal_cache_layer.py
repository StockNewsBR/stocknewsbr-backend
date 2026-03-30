import logging
import threading
import time
from typing import Dict, List

logger = logging.getLogger("stocknewsbr.cache.signal_layer")

MAX_SIGNALS = 2000


class SignalCacheLayer:
    def __init__(self):
        self._signals: List[Dict] = []
        self._timestamp: float = 0.0
        self._lock = threading.RLock()

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

        except Exception as exc:
            logger.exception("Signal cache update error: %s", exc)

    def get(self) -> List[Dict]:
        try:
            with self._lock:
                return list(self._signals)
        except Exception:
            return []

    def get_top(self, limit: int = 50) -> List[Dict]:
        try:
            with self._lock:
                return list(self._signals[:limit])
        except Exception:
            return []

    def age(self):
        ts = self._timestamp

        if ts == 0:
            return None

        return int(time.time() - ts)

    def size(self):
        try:
            with self._lock:
                return len(self._signals)
        except Exception:
            return 0

    def clear(self):
        with self._lock:
            self._signals = []
            self._timestamp = 0


signal_cache_layer = SignalCacheLayer()


def update_signal_cache(signals):
    signal_cache_layer.update(signals)


def get_signal_cache():
    return signal_cache_layer.get()


def get_top_signals(limit=50):
    return signal_cache_layer.get_top(limit)
