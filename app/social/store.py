from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict


SOCIAL_STORE_PATH = Path("runtime/social/social_state.json")
_lock = threading.RLock()


def _default_state() -> Dict[str, Any]:
    return {
        "posts": [],
        "comments": [],
        "likes": {},
        "followers": {},
        "sentiment_polls": {},
        "counters": {
            "post_id": 0,
            "comment_id": 0,
        },
    }


def _deserialize_state(payload: Any) -> Dict[str, Any]:
    state = _default_state()

    if isinstance(payload, dict):
        state.update(payload)

    state["posts"] = list(state.get("posts", []))
    state["comments"] = list(state.get("comments", []))
    state["likes"] = {
        str(key): set(value or [])
        for key, value in dict(state.get("likes", {})).items()
    }
    state["followers"] = {
        str(key): set(value or [])
        for key, value in dict(state.get("followers", {})).items()
    }
    state["sentiment_polls"] = {
        str(key): dict(value or {})
        for key, value in dict(state.get("sentiment_polls", {})).items()
    }
    state["counters"] = dict(state.get("counters", {}))
    state["counters"].setdefault("post_id", 0)
    state["counters"].setdefault("comment_id", 0)
    return state


def _serialize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "posts": list(state.get("posts", [])),
        "comments": list(state.get("comments", [])),
        "likes": {
            str(key): sorted(list(value or []))
            for key, value in dict(state.get("likes", {})).items()
        },
        "followers": {
            str(key): sorted(list(value or []))
            for key, value in dict(state.get("followers", {})).items()
        },
        "sentiment_polls": {
            str(key): dict(value or {})
            for key, value in dict(state.get("sentiment_polls", {})).items()
        },
        "counters": dict(state.get("counters", {})),
    }


def _read_from_disk() -> Dict[str, Any]:
    if not SOCIAL_STORE_PATH.exists():
        return _default_state()

    try:
        payload = json.loads(SOCIAL_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return _default_state()

    return _deserialize_state(payload)


def _write_to_disk(state: Dict[str, Any]) -> None:
    SOCIAL_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    serialized = _serialize_state(state)
    temp_path = SOCIAL_STORE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(SOCIAL_STORE_PATH)


def read_social_state(reader: Callable[[Dict[str, Any]], Any]):
    with _lock:
        state = _read_from_disk()
        return reader(state)


def mutate_social_state(mutator: Callable[[Dict[str, Any]], Any]):
    with _lock:
        state = _read_from_disk()
        result = mutator(state)
        _write_to_disk(state)
        return result
