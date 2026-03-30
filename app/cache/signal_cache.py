import time
from typing import Any, Dict, List

from app.cache.signal_cache_layer import signal_cache_layer


class SignalCacheCompatibility:
    def update(self, signals: List[Dict[str, Any]]):
        signal_cache_layer.update(signals)

    def get(self) -> List[Dict[str, Any]]:
        return signal_cache_layer.get()

    def get_all(self) -> List[Dict[str, Any]]:
        return signal_cache_layer.get()

    def get_top(self, limit: int = 50) -> List[Dict[str, Any]]:
        return signal_cache_layer.get_top(limit)

    def clear(self):
        signal_cache_layer.clear()

    def info(self) -> Dict[str, Any]:
        timestamp = getattr(signal_cache_layer, "_timestamp", 0.0) or 0.0
        age_seconds = None

        if timestamp:
            age_seconds = max(0, int(time.time() - timestamp))

        return {
            "signals": signal_cache_layer.size(),
            "timestamp": timestamp or None,
            "age_seconds": age_seconds,
        }


signal_cache = SignalCacheCompatibility()


def update_signals(signals: List[Dict[str, Any]]):
    signal_cache.update(signals)


def get_signals() -> List[Dict[str, Any]]:
    return signal_cache.get()


def get_all_signals() -> List[Dict[str, Any]]:
    return signal_cache.get_all()


def get_signal_info() -> Dict[str, Any]:
    return signal_cache.info()
