from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)


@contextmanager
def interprocess_file_lock(lock_path: Path, timeout_seconds: float = 5.0) -> Iterator[None]:
    # This OS-level lock is intentionally not reentrant; nested acquisition of
    # the same lock_path can self-block until timeout.
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_timeout = 5.0 if timeout_seconds is None else float(timeout_seconds)
    deadline = time.monotonic() + max(0.0, resolved_timeout)

    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"Could not acquire file lock: {lock_path}")
                    time.sleep(0.01)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"Could not acquire file lock: {lock_path}")
                    time.sleep(0.01)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_json_file(path: Path, default_factory: Callable[[], Any]) -> Any:
    """Reads a JSON file.

    Missing files and corrupted JSON fall back to the default state.
    Operational IO failures (permissions, hardware, etc.) propagate so real
    errors are never masked by a false fallback (Mission 31F).
    """
    try:
        if not path.exists():
            return default_factory()
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return default_factory()
    except OSError:
        logger.warning("JSON read failed for %s (operational IO error)", path, exc_info=True)
        raise

    try:
        return json.loads(raw)
    except Exception:
        logger.warning("JSON parse failed for %s; using default state", path, exc_info=True)
        return default_factory()


def read_json_file_consistent(
    path: Path,
    default_factory: Callable[[], Any],
    *,
    max_attempts: int = 3,
) -> tuple[Any, float, int]:
    """Reads a JSON file only when a stable (mtime/size/inode) snapshot is
    observed around the read.

    - Missing file: returns the default state.
    - Operational IO failures (permissions, etc.): propagate.
    - Corrupted JSON on a stable snapshot: propagates the parse error so the
      caller can mark itself degraded instead of silently using a fallback.
    - Persistent contention (file keeps changing): fails closed with
      TimeoutError instead of returning a possibly torn default (Mission 31F).
    """
    attempts = max(1, int(max_attempts or 1))

    for _ in range(attempts):
        try:
            handle = path.open("rb")
        except FileNotFoundError:
            return default_factory(), 0.0, 0

        try:
            before = os.fstat(handle.fileno())
            raw = handle.read()
            after = os.fstat(handle.fileno())
        finally:
            handle.close()

        if (
            before.st_mtime == after.st_mtime
            and before.st_size == after.st_size
            and getattr(before, "st_ino", None) == getattr(after, "st_ino", None)
        ):
            return json.loads(raw.decode("utf-8")), float(after.st_mtime), int(after.st_size)

        time.sleep(0.01)

    raise TimeoutError(f"Could not obtain a consistent read of {path}")


def write_json_file_atomic(path: Path, payload: Any, *, ensure_ascii: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=ensure_ascii, indent=2)
    tmp_name = f".{path.name}.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp"
    tmp_path = path.parent / tmp_name

    try:
        # O_EXCL guarantees the temp file is private to this writer and 0o600
        # keeps intermediate state unreadable by other users (Mission 31F).
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        if os.name != "nt":
            try:
                dir_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except Exception:
                pass
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


def mutate_json_file(
    path: Path,
    default_factory: Callable[[], Any],
    mutator: Callable[[Any], Any],
    *,
    ensure_ascii: bool = False,
    timeout_seconds: float = 5.0,
) -> Any:
    """Atomically mutates a JSON state file under an interprocess lock.

    The mutated *state* is what gets persisted; the mutator's return value is
    only the operation result handed back to the caller (Mission 31F). If the
    mutator raises, nothing is persisted. A corrupted state file propagates the
    parse error instead of being silently replaced by default-derived state.
    """
    lock_path = path.with_suffix(path.suffix + ".lock")
    with interprocess_file_lock(lock_path, timeout_seconds=timeout_seconds):
        # Mission 31F: fail closed on corrupted JSON. read_json_file would fall
        # back to the default state here, and the write below would overwrite
        # the corrupted file with default-derived data (silent data loss).
        state, _, _ = read_json_file_consistent(path, default_factory, max_attempts=1)
        result = mutator(state)
        write_json_file_atomic(path, state, ensure_ascii=ensure_ascii)
        return state if result is None else result


def write_json_file_atomic_locked(
    path: Path,
    payload: Any,
    *,
    ensure_ascii: bool = False,
    timeout_seconds: float = 5.0,
) -> None:
    """Write JSON atomically while holding an interprocess file lock."""
    target = Path(path)
    lock_path = target.with_suffix(target.suffix + ".lock")
    with interprocess_file_lock(lock_path, timeout_seconds=timeout_seconds):
        write_json_file_atomic(target, payload, ensure_ascii=ensure_ascii)
