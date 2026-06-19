import threading
import time
import json
import os
import hashlib
import atexit
import shutil
import sys
import tempfile
from typing import Any, Dict, List, Optional
from pathlib import Path

from app.services.snapshot_contract import attach_decision_envelope, summarize_snapshot_rows
from app.services.go_live_status_service import attach_go_live_status, build_go_live_status
from app.services.snapshot_runtime_status import evaluate_snapshot_runtime_status
from app.services.score_display import canonicalize_master_score_row, master_score_sort_value
from app.services.symbol_registry import canonical_symbol, canonicalize_symbol_row, dedupe_canonical_rows
from app.system.system_metrics import record_cache_lookup, record_snapshot_write_metric, update_cache_timestamp

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TEST_RUNTIME_ROOT: Path | None = None
_TEST_RUNTIME_CLEANUP_REGISTERED = False


def _project_runtime_path(env_name: str, default_relative: str) -> Path:
    configured = os.getenv(env_name)
    if configured:
        configured_path = Path(configured)
        return configured_path if configured_path.is_absolute() else _PROJECT_ROOT / configured_path
    return _PROJECT_ROOT / default_relative


def _is_test_process() -> bool:
    explicit = os.getenv("STOCKNEWSBR_TEST_MODE")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes", "on"}
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("PYTEST_VERSION"):
        return True
    argv = " ".join(str(arg).lower() for arg in sys.argv)
    return (
        "pytest" in argv
        or ("unittest" in argv and ("discover" in argv or "tests" in argv or "test_" in argv))
        or ("discover" in argv and "tests" in argv)
        or any(str(arg).lower().startswith("tests.") for arg in sys.argv)
        or any(Path(str(arg)).name.lower().startswith("test_") for arg in sys.argv)
    )


def _cleanup_test_runtime_root(path: Path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def _test_runtime_root() -> Path:
    global _TEST_RUNTIME_ROOT
    global _TEST_RUNTIME_CLEANUP_REGISTERED

    if _TEST_RUNTIME_ROOT is None:
        _TEST_RUNTIME_ROOT = Path(tempfile.gettempdir()) / "stocknewsbr-tests" / f"snapshot-cache-{os.getpid()}"
        _TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    if not _TEST_RUNTIME_CLEANUP_REGISTERED:
        atexit.register(_cleanup_test_runtime_root, _TEST_RUNTIME_ROOT)
        _TEST_RUNTIME_CLEANUP_REGISTERED = True
    return _TEST_RUNTIME_ROOT


def _snapshot_runtime_path(env_name: str, default_relative: str) -> Path:
    if os.getenv(env_name):
        return _project_runtime_path(env_name, default_relative)
    if _is_test_process():
        return _test_runtime_root() / "runtime" / "cache" / Path(default_relative).name
    return _project_runtime_path(env_name, default_relative)


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
_TOP_LEVEL_SIGNATURE_VOLATILE_KEYS = {
    "certification_timestamp",
    "generated_at",
    "go_live",
    "updated_at",
}


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
        self._storage_path = _snapshot_runtime_path("SNAPSHOT_CACHE_FILE", "runtime/cache/snapshot.json")

    def _empty_payload(self) -> Dict[str, Any]:
        return {
            "signals": [],
            "leaders": [],
            "source": "empty",
            "stale": True,
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

            row = canonicalize_symbol_row(dict(item))
            ticker = row.get("ticker") or row.get("symbol")

            if ticker:
                row["ticker"] = ticker
                row["symbol"] = ticker

            normalized.append(canonicalize_master_score_row(row))

        normalized = dedupe_canonical_rows(normalized)

        normalized.sort(
            key=master_score_sort_value,
            reverse=True,
        )

        return normalized

    def _build_by_ticker(self, signals: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        by_ticker: Dict[str, Dict[str, Any]] = {}

        for signal in signals:
            ticker = canonical_symbol(signal.get("ticker") or signal.get("symbol"))

            if ticker:
                item = canonicalize_symbol_row(dict(signal))
                by_ticker[ticker] = item

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

        source_snapshot_id = (
            payload.get("source_snapshot_id")
            or payload.get("snapshot_id")
            or payload.get("generated_at")
            or payload.get("updated_at")
            or payload.get("timestamp")
            or payload.get("source")
            or "snapshot_cache"
        )
        envelope_timestamp = payload.get("generated_at") or payload.get("updated_at") or payload.get("timestamp") or source_snapshot_id
        signals = [
            attach_decision_envelope(
                row,
                snapshot_stale=bool(payload.get("stale") is True),
                source_snapshot_id=source_snapshot_id,
                timestamp=envelope_timestamp,
            )
            for row in signals
        ]
        derived_stats = summarize_snapshot_rows(signals)
        existing_stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
        payload["signals"] = signals
        payload["leaders"] = signals[:20]
        payload["by_ticker"] = self._build_by_ticker(signals)
        payload["stats"] = {**existing_stats, **derived_stats}
        for key in (
            "master_score",
            "strategic_panel",
            "historical_confidence",
            "institutional_conviction",
            "institutional_priority",
            "final_decision",
            "decision_envelope",
        ):
            if isinstance(payload.get(key), dict):
                payload[key] = canonicalize_master_score_row(dict(payload[key]))
        for key in (
            "master_scores",
            "strategic_panels",
            "institutional_radar",
            "institutional_ranking",
            "historical_confidences",
            "operational_rules",
            "institutional_convictions",
            "institutional_priorities",
            "final_decisions",
            "decision_envelopes",
        ):
            if isinstance(payload.get(key), list):
                payload[key] = [
                    canonicalize_master_score_row(dict(row))
                    for row in payload[key]
                    if isinstance(row, dict)
                ]

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
        for key in (
            "auditor",
            "institutional_auditor",
            "master_score",
            "strategic_panel",
            "historical_confidence",
            "institutional_conviction",
            "institutional_priority",
            "final_decision",
            "institutional_consistency",
            "decision_envelope",
        ):
            if isinstance(payload.get(key), dict):
                cloned[key] = canonicalize_master_score_row(dict(payload.get(key, {})))
        for key in ("master_scores", "strategic_panels", "institutional_radar", "institutional_ranking", "historical_confidences", "operational_rules", "institutional_convictions", "institutional_priorities", "final_decisions", "decision_envelopes"):
            if isinstance(payload.get(key), list):
                cloned[key] = [canonicalize_master_score_row(dict(row)) for row in payload.get(key, []) if isinstance(row, dict)]
        for key in ("radar_metrics", "ranking_metrics", "historical_confidence_metrics", "operational_rules_metrics", "conviction_metrics", "priority_metrics", "final_decision_metrics", "institutional_consistency_metrics"):
            if isinstance(payload.get(key), dict):
                cloned[key] = dict(payload.get(key, {}))
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
        normalized = attach_go_live_status(normalized, now=now)
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
            if should_write:
                write_ok = self._write_to_disk()
                record_snapshot_write_metric(write_ok)
                if write_ok:
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
                canonical_ticker = canonical_symbol(ticker)
                row = by_ticker.get(canonical_ticker) or by_ticker.get(ticker)
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
            payload = self._clone_payload(self._payload)
            last_good_timestamp = self._last_good_timestamp or None
            last_good_signals = len(self._last_good_payload.get("signals", []))
            last_good_source = self._last_good_payload.get("source")
            last_good_generated_at = self._last_good_payload.get("generated_at")

        age_seconds = None

        if timestamp:
            age_seconds = max(0, int(time.time() - timestamp))

        last_good_age_seconds = None

        if last_good_timestamp:
            last_good_age_seconds = max(0, int(time.time() - last_good_timestamp))

        runtime_snapshot = {
            **payload,
            "timestamp": timestamp,
            "age_seconds": age_seconds,
            "last_good_signals": last_good_signals,
            "last_good_timestamp": last_good_timestamp,
        }
        runtime_status = evaluate_snapshot_runtime_status(runtime_snapshot)
        go_live = build_go_live_status(runtime_snapshot)
        info = {
            "signals": signal_count,
            "timestamp": timestamp,
            "age_seconds": age_seconds,
            "has_signals": signal_count > 0,
            "is_empty": signal_count == 0,
            "source": payload.get("source"),
            "stale": bool(payload.get("stale")),
            "snapshot_runtime_status": runtime_status["status"],
            "snapshot_runtime": runtime_status,
            "fallback_active": bool(runtime_status.get("fallback_active")),
            "go_live_ready": bool(go_live.get("go_live_ready")),
            "go_live": go_live,
            "institutional_consistency_score": go_live.get("institutional_consistency_score"),
            "contract_coverage": go_live.get("contract_coverage", {}),
            "institutional_certified": bool(go_live.get("institutional_certified")),
            "certification_timestamp": go_live.get("certification_timestamp"),
            "certification_reasons": list(go_live.get("certification_reasons") or []),
            "last_good_signals": last_good_signals,
            "last_good_timestamp": last_good_timestamp,
            "last_good_age_seconds": last_good_age_seconds,
            "last_good_available": last_good_signals > 0,
            "last_good_snapshot": {
                "signals": last_good_signals,
                "timestamp": last_good_timestamp,
                "age_seconds": last_good_age_seconds,
                "source": last_good_source,
                "generated_at": last_good_generated_at,
                "available": last_good_signals > 0,
            },
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
                canonical_ticker = canonical_symbol(ticker)
                row = by_ticker.get(canonical_ticker) or by_ticker.get(ticker)
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
