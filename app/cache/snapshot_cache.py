import threading
import time
from typing import Any, Dict, List, Optional

from app.system.system_metrics import update_cache_timestamp


_RESERVED_KEYS = {
    "signals",
    "leaders",
    "stats",
    "by_ticker",
    "generated_at",
    "updated_at",
}


class SnapshotCache:
    def __init__(self):
        self._payload: Dict[str, Any] = self._empty_payload()
        self._timestamp: float = 0.0
        self._lock = threading.RLock()

    def _empty_payload(self) -> Dict[str, Any]:
        return {
            "signals": [],
            "leaders": [],
            "stats": {
                "total_signals": 0,
                "bullish": 0,
                "bearish": 0,
            },
            "by_ticker": {},
        }

    def _normalize_signals(self, signals: Any) -> List[Dict[str, Any]]:
        if not isinstance(signals, list):
            return []

        normalized: List[Dict[str, Any]] = []

        for item in signals:
            if not isinstance(item, dict):
                continue

            row = dict(item)
            ticker = row.get("ticker") or row.get("symbol")

            if ticker:
                row["ticker"] = ticker
                row["symbol"] = ticker

            normalized.append(row)

        normalized.sort(
            key=lambda row: float(row.get("score", 0) or 0),
            reverse=True,
        )

        return normalized

    def _build_by_ticker(self, signals: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        by_ticker: Dict[str, Dict[str, Any]] = {}

        for signal in signals:
            ticker = signal.get("ticker") or signal.get("symbol")

            if ticker:
                by_ticker[ticker] = dict(signal)

        return by_ticker

    def _derive_signals_from_payload(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        explicit_signals = payload.get("signals")

        if isinstance(explicit_signals, list):
            return self._normalize_signals(explicit_signals)

        candidate_rows = []

        for key, value in payload.items():
            if key in _RESERVED_KEYS or not isinstance(value, dict):
                continue

            row = dict(value)
            row.setdefault("ticker", key)
            row.setdefault("symbol", key)
            candidate_rows.append(row)

        return self._normalize_signals(candidate_rows)

    def _normalize_payload(self, data: Any) -> Dict[str, Any]:
        if isinstance(data, dict):
            payload = dict(data)
            signals = self._derive_signals_from_payload(payload)
        elif isinstance(data, list):
            payload = {}
            signals = self._normalize_signals(data)
        else:
            return self._empty_payload()

        bullish = 0
        bearish = 0

        for signal in signals:
            try:
                score = float(signal.get("score", 0) or 0)
            except Exception:
                score = 0.0

            if score >= 70:
                bullish += 1
            elif score <= 30:
                bearish += 1

        payload["signals"] = signals
        payload["leaders"] = signals[:20]
        payload["by_ticker"] = self._build_by_ticker(signals)
        payload["stats"] = {
            "total_signals": len(signals),
            "bullish": bullish,
            "bearish": bearish,
        }

        return payload

    def update(self, data: Any):
        normalized = self._normalize_payload(data)

        with self._lock:
            self._payload = normalized
            self._timestamp = time.time()
            self._payload["updated_at"] = self._timestamp
            self._payload.setdefault("generated_at", self._timestamp)

        update_cache_timestamp(self._timestamp)

    def get(self) -> Dict[str, Any]:
        with self._lock:
            payload = dict(self._payload)
            payload["signals"] = list(self._payload.get("signals", []))
            payload["leaders"] = list(self._payload.get("leaders", []))
            payload["by_ticker"] = {
                key: dict(value)
                for key, value in self._payload.get("by_ticker", {}).items()
            }
            payload["stats"] = dict(self._payload.get("stats", {}))
            return payload

    def get_signals(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            signals = list(self._payload.get("signals", []))

        if limit is None:
            return signals

        return signals[:limit]

    def get_by_ticker(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {
                key: dict(value)
                for key, value in self._payload.get("by_ticker", {}).items()
            }

    def info(self) -> Dict[str, Any]:
        with self._lock:
            timestamp = self._timestamp or None
            signal_count = len(self._payload.get("signals", []))

        age_seconds = None

        if timestamp:
            age_seconds = max(0, int(time.time() - timestamp))

        return {
            "signals": signal_count,
            "timestamp": timestamp,
            "age_seconds": age_seconds,
        }

    def clear(self):
        with self._lock:
            self._payload = self._empty_payload()
            self._timestamp = 0.0


snapshot_cache = SnapshotCache()


def update_snapshot(data: Any):
    snapshot_cache.update(data)


def get_snapshot() -> Dict[str, Any]:
    return snapshot_cache.get()


def get_snapshot_signals(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    return snapshot_cache.get_signals(limit=limit)


def get_snapshot_by_ticker() -> Dict[str, Dict[str, Any]]:
    return snapshot_cache.get_by_ticker()


def get_snapshot_info() -> Dict[str, Any]:
    return snapshot_cache.info()
