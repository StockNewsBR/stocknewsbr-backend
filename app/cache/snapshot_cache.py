import threading
import time
import json
import os
import hashlib
from typing import Any, Dict, List, Optional
from pathlib import Path

from app.services.snapshot_contract import summarize_snapshot_rows
from app.system.system_metrics import record_cache_lookup, update_cache_timestamp

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _project_runtime_path(env_name: str, default_relative: str) -> Path:
    configured = os.getenv(env_name)
    if configured:
        configured_path = Path(configured)
        return configured_path if configured_path.is_absolute() else _PROJECT_ROOT / configured_path
    return _PROJECT_ROOT / default_relative


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
_TOP_LEVEL_SIGNATURE_VOLATILE_KEYS = {"generated_at", "updated_at"}


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default)) or default))
    except (TypeError, ValueError):
        return default


SNAPSHOT_DISK_WRITE_MIN_INTERVAL_SECONDS = _env_float("SNAPSHOT_DISK_WRITE_MIN_INTERVAL_SECONDS", 1.0)


class SnapshotCache:
    def __init__(self):
        self._payload: Dict[str, Any] = self._empty_payload()
        self._timestamp: float = 0.0
        self._last_good_payload: Dict[str, Any] = self._empty_payload()
        self._last_good_timestamp: float = 0.0
        self._disk_mtime: float = 0.0
        self._last_disk_write_at: float = 0.0
        self._last_disk_signature: str = ""
        self._last_good_signature: str = ""
        self._disk_write_min_interval_seconds = SNAPSHOT_DISK_WRITE_MIN_INTERVAL_SECONDS
        self._lock = threading.RLock()
        self._storage_path = _project_runtime_path("SNAPSHOT_CACHE_FILE", "runtime/cache/snapshot.json")

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
            key=lambda row: float(row.get("master_score", row.get("score", 0)) or 0),
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

        derived_stats = summarize_snapshot_rows(signals)
        existing_stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
        payload["signals"] = signals
        payload["leaders"] = signals[:20]
        payload["by_ticker"] = self._build_by_ticker(signals)
        payload["stats"] = {**existing_stats, **derived_stats}

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
            return True
        except Exception:
            return False

    def _payload_signature(self, payload: Dict[str, Any]) -> str:
        stable_payload = {
            key: value
            for key, value in payload.items()
            if key not in _TOP_LEVEL_SIGNATURE_VOLATILE_KEYS
        }
        try:
            serialized = json.dumps(
                stable_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
        except Exception:
            serialized = repr(stable_payload)
        return hashlib.sha1(serialized.encode("utf-8", errors="replace")).hexdigest()

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
                self._last_disk_write_at = file_mtime
                self._last_disk_signature = self._payload_signature(payload)
                self._last_good_signature = self._payload_signature(last_good_payload)
        except Exception:
            pass

    def update(self, data: Any):
        normalized = self._normalize_payload(data)
        if not normalized.get("signals") and self._payload.get("signals"):
            # Preserve the last good live payload when an empty update arrives.
            # This keeps transient provider gaps from blanking the shared cache.
            return
        now = time.time()
        normalized["updated_at"] = now
        normalized.setdefault("generated_at", now)
        signature = self._payload_signature(normalized)

        with self._lock:
            self._payload = normalized
            self._timestamp = now
            if self._is_promotable_last_good(self._payload):
                if signature != self._last_good_signature:
                    self._last_good_payload = self._clone_payload(self._payload)
                    self._last_good_signature = signature
                else:
                    self._last_good_payload["updated_at"] = self._payload.get("updated_at")
                    self._last_good_payload["generated_at"] = self._payload.get("generated_at")
                self._last_good_timestamp = self._timestamp
            should_write = (
                not self._last_disk_write_at
                or signature != self._last_disk_signature
                or now - self._last_disk_write_at >= self._disk_write_min_interval_seconds
            )
            if should_write and self._write_to_disk():
                self._last_disk_write_at = now
                self._last_disk_signature = signature

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
            self._last_disk_write_at = 0.0
            self._last_disk_signature = ""
            self._last_good_signature = ""
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
