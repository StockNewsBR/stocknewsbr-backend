from __future__ import annotations

import atexit
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict

from app.core.atomic_io import read_json_file_consistent, write_json_file_atomic

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TEST_RUNTIME_ROOT: Path | None = None
_TEST_RUNTIME_CLEANUP_REGISTERED = False


def _is_test_process() -> bool:
    explicit = os.getenv("STOCKNEWSBR_TEST_MODE")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes", "on"}
    argv = " ".join(str(arg).lower() for arg in sys.argv)
    return (
        "pytest" in argv
        or ("unittest" in argv and ("discover" in argv or "tests" in argv or "test_" in argv))
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
        _TEST_RUNTIME_ROOT = Path(tempfile.gettempdir()) / "stocknewsbr-tests" / f"signal-outcomes-{os.getpid()}"
        _TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    if not _TEST_RUNTIME_CLEANUP_REGISTERED:
        atexit.register(_cleanup_test_runtime_root, _TEST_RUNTIME_ROOT)
        _TEST_RUNTIME_CLEANUP_REGISTERED = True
    return _TEST_RUNTIME_ROOT


def _outcome_runtime_path() -> Path:
    configured = os.getenv("SIGNAL_OUTCOME_STATE_FILE")
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else _PROJECT_ROOT / path
    if _is_test_process():
        return _test_runtime_root() / "runtime" / "cache" / "signal_outcomes.json"
    return _PROJECT_ROOT / "runtime" / "cache" / "signal_outcomes.json"


def empty_signal_outcome_metrics() -> Dict[str, Any]:
    return {
        "total_signals": 0,
        "executable_signals": 0,
        "blocked_signals": 0,
        "skipped_signals": 0,
        "insufficient_data": 0,
        "evaluated_executable_signals": 0,
        "winner_signals": 0,
        "loser_signals": 0,
        "neutral_signals": 0,
        "win_rate": 0.0,
        "average_mfe_pct": 0.0,
        "average_mae_pct": 0.0,
        "average_payoff": 0.0,
        "simulated_drawdown_pct": 0.0,
        "block_rate": 0.0,
        "false_positive_rate": 0.0,
        "false_negative_rate": 0.0,
        "insufficient_data_rate": 0.0,
        "blocked_would_have_won": 0,
        "blocked_correctly": 0,
        "released_failed": 0,
        "released_won": 0,
        "by_symbol": {},
        "by_regime": {},
        "by_score_bucket": {},
        "last_update_timestamp": None,
    }


def empty_signal_outcome_state() -> Dict[str, Any]:
    return {
        "mode": "PAPER_ONLY",
        "simulation": "SIMULATED",
        "signal_outcome_status": "IDLE",
        "records": [],
        "metrics": empty_signal_outcome_metrics(),
        "windows_seconds": {"5m": 300, "15m": 900, "30m": 1800, "60m": 3600},
        "last_update_timestamp": None,
    }


def _clone(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return empty_signal_outcome_state()


def _normalize_state(state: Any) -> Dict[str, Any]:
    if not isinstance(state, dict):
        return empty_signal_outcome_state()

    normalized = empty_signal_outcome_state()
    normalized.update({key: value for key, value in state.items() if key in normalized or key == "state_error"})
    normalized["mode"] = "PAPER_ONLY"
    normalized["simulation"] = "SIMULATED"
    normalized["records"] = [dict(item) for item in normalized.get("records", []) if isinstance(item, dict)]
    metrics = normalized.get("metrics") if isinstance(normalized.get("metrics"), dict) else {}
    normalized["metrics"] = {**empty_signal_outcome_metrics(), **metrics}
    windows = normalized.get("windows_seconds") if isinstance(normalized.get("windows_seconds"), dict) else {}
    normalized["windows_seconds"] = {**empty_signal_outcome_state()["windows_seconds"], **windows}
    normalized["last_update_timestamp"] = normalized["metrics"].get("last_update_timestamp") or normalized.get("last_update_timestamp")
    return normalized


class SignalOutcomeCache:
    def __init__(self, storage_path: Path | None = None):
        self._storage_path = storage_path or _outcome_runtime_path()
        self._lock = threading.RLock()
        self._state = empty_signal_outcome_state()
        self._disk_mtime = 0.0
        self._load_from_disk()

    @property
    def storage_path(self) -> Path:
        return self._storage_path

    def _ensure_storage_dir(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_from_disk(self) -> None:
        try:
            if not self._storage_path.exists():
                return
            raw, stable_mtime, _stable_size = read_json_file_consistent(
                self._storage_path,
                empty_signal_outcome_state,
            )
            with self._lock:
                if stable_mtime and stable_mtime <= self._disk_mtime:
                    # Mission 31F: leitura stale do disco não pode sobrescrever
                    # estado em memória mais novo.
                    return
                self._state = _normalize_state(raw)
                self._disk_mtime = stable_mtime or self._storage_path.stat().st_mtime
        except Exception:
            with self._lock:
                self._state = empty_signal_outcome_state()
                self._state["signal_outcome_status"] = "DEGRADED"
                self._state["state_error"] = "state_file_corrupted"

    def get(self) -> Dict[str, Any]:
        try:
            if self._storage_path.exists():
                file_mtime = self._storage_path.stat().st_mtime
                if file_mtime > self._disk_mtime:
                    self._load_from_disk()
        except Exception:
            pass
        with self._lock:
            return _clone(self._state)

    def update(self, state: Dict[str, Any]) -> Dict[str, Any]:
        normalized = _normalize_state(state)
        # Mission 31F: a escrita em disco precisa ficar dentro do lock; fora
        # dele, duas atualizações concorrentes podiam terminar com memória=A e
        # disco=B (divergência entre estado em memória e persistido).
        with self._lock:
            self._state = normalized
            try:
                self._ensure_storage_dir()
                write_json_file_atomic(self._storage_path, normalized, ensure_ascii=False)
                self._disk_mtime = self._storage_path.stat().st_mtime
            except Exception:
                self._state["signal_outcome_status"] = "DEGRADED"
                self._state["state_error"] = "state_write_failed"
            return _clone(self._state)

    def reset(self) -> Dict[str, Any]:
        state = empty_signal_outcome_state()
        state["last_update_timestamp"] = time.time()
        state["metrics"]["last_update_timestamp"] = state["last_update_timestamp"]
        return self.update(state)


signal_outcome_cache = SignalOutcomeCache()


def get_signal_outcome_state() -> Dict[str, Any]:
    return signal_outcome_cache.get()


def update_signal_outcome_state(state: Dict[str, Any]) -> Dict[str, Any]:
    return signal_outcome_cache.update(state)


def reset_signal_outcome_state() -> Dict[str, Any]:
    return signal_outcome_cache.reset()
