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
        _TEST_RUNTIME_ROOT = Path(tempfile.gettempdir()) / "stocknewsbr-tests" / f"paper-trading-{os.getpid()}"
        _TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    if not _TEST_RUNTIME_CLEANUP_REGISTERED:
        atexit.register(_cleanup_test_runtime_root, _TEST_RUNTIME_ROOT)
        _TEST_RUNTIME_CLEANUP_REGISTERED = True
    return _TEST_RUNTIME_ROOT


def _paper_runtime_path() -> Path:
    configured = os.getenv("PAPER_TRADING_STATE_FILE")
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else _PROJECT_ROOT / path
    if _is_test_process():
        return _test_runtime_root() / "runtime" / "cache" / "paper_trading.json"
    return _PROJECT_ROOT / "runtime" / "cache" / "paper_trading.json"


def _empty_metrics() -> Dict[str, Any]:
    return {
        "total_trades": 0,
        "open_trades": 0,
        "closed_trades": 0,
        "win_rate": 0.0,
        "avg_return_pct": 0.0,
        "total_return_pct": 0.0,
        "max_win_pct": 0.0,
        "max_loss_pct": 0.0,
        "skipped_signals": 0,
        "skipped_reasons": {},
        "last_update_timestamp": None,
    }


def empty_paper_trading_state() -> Dict[str, Any]:
    return {
        "mode": "PAPER_ONLY",
        "simulation": "SIMULATED",
        "paper_trading_enabled": True,
        "paper_trading_status": "IDLE",
        "positions": [],
        "trades": [],
        "skipped": [],
        "metrics": _empty_metrics(),
        "last_update_timestamp": None,
    }


def _clone(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return empty_paper_trading_state()


def _normalize_state(state: Any) -> Dict[str, Any]:
    if not isinstance(state, dict):
        return empty_paper_trading_state()

    normalized = empty_paper_trading_state()
    normalized.update({key: value for key, value in state.items() if key in normalized or key == "state_error"})
    normalized["mode"] = "PAPER_ONLY"
    normalized["simulation"] = "SIMULATED"
    normalized["positions"] = [dict(item) for item in normalized.get("positions", []) if isinstance(item, dict)]
    normalized["trades"] = [dict(item) for item in normalized.get("trades", []) if isinstance(item, dict)]
    normalized["skipped"] = [dict(item) for item in normalized.get("skipped", []) if isinstance(item, dict)]
    metrics = normalized.get("metrics") if isinstance(normalized.get("metrics"), dict) else {}
    normalized["metrics"] = {**_empty_metrics(), **metrics}
    normalized["last_update_timestamp"] = normalized["metrics"].get("last_update_timestamp") or normalized.get("last_update_timestamp")
    return normalized


class PaperTradingCache:
    def __init__(self, storage_path: Path | None = None):
        self._storage_path = storage_path or _paper_runtime_path()
        self._lock = threading.RLock()
        self._state = empty_paper_trading_state()
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
            raw = json.loads(self._storage_path.read_text(encoding="utf-8"))
            with self._lock:
                self._state = _normalize_state(raw)
                self._disk_mtime = self._storage_path.stat().st_mtime
        except Exception:
            with self._lock:
                self._state = empty_paper_trading_state()
                self._state["paper_trading_status"] = "DEGRADED"
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
        with self._lock:
            self._state = normalized
            try:
                self._ensure_storage_dir()
                temp_path = self._storage_path.with_suffix(".tmp")
                temp_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
                temp_path.replace(self._storage_path)
                self._disk_mtime = self._storage_path.stat().st_mtime
            except Exception:
                self._state["paper_trading_status"] = "DEGRADED"
                self._state["state_error"] = "state_write_failed"
            return _clone(self._state)

    def reset(self) -> Dict[str, Any]:
        state = empty_paper_trading_state()
        state["last_update_timestamp"] = time.time()
        state["metrics"]["last_update_timestamp"] = state["last_update_timestamp"]
        return self.update(state)


paper_trading_cache = PaperTradingCache()


def get_paper_trading_state() -> Dict[str, Any]:
    return paper_trading_cache.get()


def update_paper_trading_state(state: Dict[str, Any]) -> Dict[str, Any]:
    return paper_trading_cache.update(state)


def reset_paper_trading_state() -> Dict[str, Any]:
    return paper_trading_cache.reset()
