import threading
import time
import json
import os
from typing import Any, Dict, List, Optional
from pathlib import Path

from app.system.system_metrics import record_cache_lookup, update_cache_timestamp


_RESERVED_KEYS = {
    "signals",
    "leaders",
    "stats",
    "by_ticker",
    "generated_at",
    "updated_at",
}

_STALE_SOURCES = {
    "snapshot_fallback",
    "exception_fallback",
    "empty",
    "exception",
}


class SnapshotCache:
    def __init__(self):
        self._payload: Dict[str, Any] = self._empty_payload()
        self._timestamp: float = 0.0
        self._last_good_payload: Dict[str, Any] = self._empty_payload()
        self._last_good_timestamp: float = 0.0
        self._disk_mtime: float = 0.0
        self._lock = threading.RLock()
        self._storage_path = Path(os.getenv("SNAPSHOT_CACHE_FILE", "runtime/cache/snapshot.json"))

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

    def _is_promotable_last_good(self, payload: Dict[str, Any]) -> bool:
        if len(payload.get("signals", [])) <= 0:
            return False
        if bool(payload.get("stale")):
            return False

        source = str(payload.get("source") or "").strip().lower()
        if source in _STALE_SOURCES:
            return False
        return True

    def _clone_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        cloned = dict(payload)
        cloned["signals"] = list(payload.get("signals", []))
        cloned["leaders"] = list(payload.get("leaders", []))
        cloned["stats"] = dict(payload.get("stats", {}))
        cloned["by_ticker"] = {
            key: dict(value)
            for key, value in payload.get("by_ticker", {}).items()
        }
        ai_tools = payload.get("ai_tools")
        if isinstance(ai_tools, dict):
            cloned["ai_tools"] = {
                key: [dict(row) for row in value if isinstance(row, dict)]
                for key, value in ai_tools.items()
                if isinstance(value, list)
            }
        return cloned

    def _ensure_storage_dir(self):
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

    def _write_to_disk(self):
        try:
            self._ensure_storage_dir()
            payload = {
                "timestamp": self._timestamp,
                "payload": self._clone_payload(self._payload),
                "last_good_timestamp": self._last_good_timestamp,
                "last_good_payload": self._clone_payload(self._last_good_payload),
            }
            temp_path = self._storage_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_path.replace(self._storage_path)
            self._disk_mtime = self._storage_path.stat().st_mtime
        except Exception:
            pass

    def _load_from_disk_if_needed(self):
        try:
            if not self._storage_path.exists():
                return

            file_mtime = self._storage_path.stat().st_mtime
            should_reload = file_mtime > self._disk_mtime or (self._timestamp == 0.0 and file_mtime > 0)
            if not should_reload:
                return

            raw = json.loads(self._storage_path.read_text(encoding="utf-8"))
            payload = self._normalize_payload(raw.get("payload"))
            last_good_payload = self._normalize_payload(raw.get("last_good_payload"))
            timestamp = float(raw.get("timestamp") or 0.0)
            last_good_timestamp = float(raw.get("last_good_timestamp") or 0.0)

            with self._lock:
                self._payload = payload
                self._timestamp = timestamp
                self._last_good_payload = last_good_payload
                self._last_good_timestamp = last_good_timestamp
                self._disk_mtime = file_mtime
        except Exception:
            pass

    def update(self, data: Any):
        normalized = self._normalize_payload(data)

        with self._lock:
            self._payload = normalized
            self._timestamp = time.time()
            self._payload["updated_at"] = self._timestamp
            self._payload.setdefault("generated_at", self._timestamp)
            if self._is_promotable_last_good(self._payload):
                self._last_good_payload = self._clone_payload(self._payload)
                self._last_good_timestamp = self._timestamp
            self._write_to_disk()

        update_cache_timestamp(self._timestamp)

    def get(self) -> Dict[str, Any]:
        start = time.perf_counter()
        self._load_from_disk_if_needed()
        with self._lock:
            payload = self._clone_payload(self._payload)
        record_cache_lookup("snapshot", time.perf_counter() - start, len(payload.get("signals", [])))
        return payload

    def get_signals(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        start = time.perf_counter()
        self._load_from_disk_if_needed()
        with self._lock:
            signals = list(self._payload.get("signals", []))
        record_cache_lookup("snapshot_signals", time.perf_counter() - start, len(signals))

        if limit is None:
            return signals

        return signals[:limit]

    def get_by_ticker(self) -> Dict[str, Dict[str, Any]]:
        start = time.perf_counter()
        self._load_from_disk_if_needed()
        with self._lock:
            payload = {
                key: dict(value)
                for key, value in self._payload.get("by_ticker", {}).items()
            }
        record_cache_lookup("snapshot_by_ticker", time.perf_counter() - start, len(payload))
        return payload

    def get_first_by_ticker(self, tickers: List[str]) -> Optional[Dict[str, Any]]:
        start = time.perf_counter()
        result = None
        size = 0
        self._load_from_disk_if_needed()
        with self._lock:
            by_ticker = self._payload.get("by_ticker", {})
            if not isinstance(by_ticker, dict):
                record_cache_lookup("snapshot_by_ticker", time.perf_counter() - start, size)
                return None
            size = len(by_ticker)

            for ticker in tickers or []:
                row = by_ticker.get(ticker)
                if isinstance(row, dict):
                    result = dict(row)
                    break

        record_cache_lookup("snapshot_by_ticker", time.perf_counter() - start, size)
        return result

    def info(self) -> Dict[str, Any]:
        start = time.perf_counter()
        self._load_from_disk_if_needed()
        with self._lock:
            timestamp = self._timestamp or None
            signal_count = len(self._payload.get("signals", []))
            last_good_timestamp = self._last_good_timestamp or None
            last_good_signals = len(self._last_good_payload.get("signals", []))

        age_seconds = None

        if timestamp:
            age_seconds = max(0, int(time.time() - timestamp))

        last_good_age_seconds = None

        if last_good_timestamp:
            last_good_age_seconds = max(0, int(time.time() - last_good_timestamp))

        info = {
            "signals": signal_count,
            "timestamp": timestamp,
            "age_seconds": age_seconds,
            "has_signals": signal_count > 0,
            "is_empty": signal_count == 0,
            "last_good_signals": last_good_signals,
            "last_good_timestamp": last_good_timestamp,
            "last_good_age_seconds": last_good_age_seconds,
        }
        record_cache_lookup("snapshot_info", time.perf_counter() - start, signal_count)
        return info

    def clear(self):
        with self._lock:
            self._payload = self._empty_payload()
            self._timestamp = 0.0
            self._last_good_payload = self._empty_payload()
            self._last_good_timestamp = 0.0
            self._disk_mtime = 0.0
        try:
            if self._storage_path.exists():
                self._storage_path.unlink()
        except Exception:
            pass

    def get_last_good(self) -> Dict[str, Any]:
        start = time.perf_counter()
        self._load_from_disk_if_needed()
        with self._lock:
            payload = self._clone_payload(self._last_good_payload)
            payload["last_good_timestamp"] = self._last_good_timestamp or None
        record_cache_lookup("snapshot_last_good", time.perf_counter() - start, len(payload.get("signals", [])))
        return payload

    def get_first_last_good_by_ticker(self, tickers: List[str]) -> Optional[Dict[str, Any]]:
        start = time.perf_counter()
        result = None
        size = 0
        self._load_from_disk_if_needed()
        with self._lock:
            by_ticker = self._last_good_payload.get("by_ticker", {})
            if not isinstance(by_ticker, dict):
                record_cache_lookup("snapshot_last_good_by_ticker", time.perf_counter() - start, size)
                return None
            size = len(by_ticker)

            for ticker in tickers or []:
                row = by_ticker.get(ticker)
                if isinstance(row, dict):
                    result = dict(row)
                    break

        record_cache_lookup("snapshot_last_good_by_ticker", time.perf_counter() - start, size)
        return result


snapshot_cache = SnapshotCache()


def update_snapshot(data: Any):
    snapshot_cache.update(data)


def get_snapshot() -> Dict[str, Any]:
    return snapshot_cache.get()


def get_snapshot_signals(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    return snapshot_cache.get_signals(limit=limit)


def get_snapshot_by_ticker() -> Dict[str, Dict[str, Any]]:
    return snapshot_cache.get_by_ticker()


def get_snapshot_ticker(candidates: List[str]) -> Optional[Dict[str, Any]]:
    return snapshot_cache.get_first_by_ticker(candidates)


def get_snapshot_info() -> Dict[str, Any]:
    return snapshot_cache.info()


def get_last_good_snapshot() -> Dict[str, Any]:
    return snapshot_cache.get_last_good()


def get_last_good_snapshot_ticker(candidates: List[str]) -> Optional[Dict[str, Any]]:
    return snapshot_cache.get_first_last_good_by_ticker(candidates)
