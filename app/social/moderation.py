# =====================================================
# MODERATION ENGINE (ADVANCED SAFE VERSION)
# =====================================================

import json
import os
import threading
import time
from pathlib import Path

from app.system.system_metrics import increment_reports


MODERATION_STORE_PATH = Path("data/moderation_state.json")
REPORT_THRESHOLD_AUTO_HIDE = max(2, int(os.getenv("MODERATION_REPORT_THRESHOLD", "4")))
POST_WINDOW_SECONDS = max(30, int(os.getenv("MODERATION_POST_WINDOW_SECONDS", "60")))
POST_WINDOW_LIMIT = max(3, int(os.getenv("MODERATION_POST_WINDOW_LIMIT", "12")))
BLOCKED_PHRASES = {
    phrase.strip().lower()
    for phrase in os.getenv("MODERATION_BLOCKED_PHRASES", "golpe,scam,spam").split(",")
    if phrase.strip()
}

_lock = threading.RLock()


def _default_state():
    return {
        "muted": {},
        "blocked": {},
        "reports": [],
        "post_rate": {},
        "shadow_banned": [],
        "review_queue": [],
        "reviewed_reports": [],
    }


def _load_state():
    with _lock:
        if not MODERATION_STORE_PATH.exists():
            return _default_state()

        try:
            data = json.loads(MODERATION_STORE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return _default_state()

        base = _default_state()
        base.update(data if isinstance(data, dict) else {})
        return base


def _save_state(state):
    with _lock:
        MODERATION_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        MODERATION_STORE_PATH.write_text(
            json.dumps(state, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )


def mute(user_id, target):
    if not user_id or not target:
        return False

    state = _load_state()
    muted = state.setdefault("muted", {})
    muted.setdefault(str(user_id), [])

    if target not in muted[str(user_id)]:
        muted[str(user_id)].append(target)

    _save_state(state)
    return True


def block(user_id, target):
    if not user_id or not target:
        return False

    state = _load_state()
    blocked = state.setdefault("blocked", {})
    blocked.setdefault(str(user_id), [])

    if target not in blocked[str(user_id)]:
        blocked[str(user_id)].append(target)

    _save_state(state)
    return True


def get_blocked_users(user_id):
    if not user_id:
        return set()

    state = _load_state()
    blocked = state.get("blocked", {})
    return set(blocked.get(str(user_id), []))


def _flag_reasons(text: str):
    text = (text or "").lower()
    return [phrase for phrase in BLOCKED_PHRASES if phrase in text]


def can_publish(user_id: int, text: str):
    if not user_id:
        return False, "invalid_user"

    state = _load_state()

    if user_id in state.get("shadow_banned", []):
        return False, "user_shadow_banned"

    flagged_phrases = _flag_reasons(text)
    if flagged_phrases:
        return False, "blocked_phrase_detected"

    now = int(time.time())
    post_rate = state.setdefault("post_rate", {})
    timestamps = [
        ts
        for ts in post_rate.get(str(user_id), [])
        if now - int(ts) <= POST_WINDOW_SECONDS
    ]

    if len(timestamps) >= POST_WINDOW_LIMIT:
        return False, "rate_limited"

    timestamps.append(now)
    post_rate[str(user_id)] = timestamps
    _save_state(state)
    return True, "allowed"


def report(user_id, post_id, reason: str | None = None, reporter_note: str | None = None):
    if not user_id or post_id is None:
        return False

    state = _load_state()
    reports = state.setdefault("reports", [])
    queue = state.setdefault("review_queue", [])

    report_item = {
        "id": f"report-{int(time.time() * 1000)}-{user_id}",
        "user": user_id,
        "post": post_id,
        "reason": reason or "general",
        "note": reporter_note,
        "created_at": int(time.time()),
    }

    reports.append(report_item)
    increment_reports()

    report_count = len([item for item in reports if item.get("post") == post_id])

    queue_item = {
        "post_id": post_id,
        "reports": report_count,
        "auto_hidden": report_count >= REPORT_THRESHOLD_AUTO_HIDE,
        "last_reason": report_item["reason"],
        "updated_at": int(time.time()),
    }

    queue = [item for item in queue if item.get("post_id") != post_id]
    queue.append(queue_item)

    state["reports"] = reports[-20000:]
    state["review_queue"] = queue[-5000:]
    _save_state(state)
    return True


def get_review_queue(limit: int = 100):
    state = _load_state()
    items = list(state.get("review_queue", []))
    return items[-max(1, min(limit, 500)) :]


def is_post_hidden(post_id: int):
    state = _load_state()

    for item in reversed(state.get("reviewed_reports", [])):
        if item.get("post_id") == post_id:
            return item.get("action") in {"hide", "remove"}

    for item in reversed(state.get("review_queue", [])):
        if item.get("post_id") == post_id:
            return bool(item.get("auto_hidden"))

    return False


def review_report(post_id: int, action: str, moderator_id: int | None = None):
    state = _load_state()
    queue = [item for item in state.get("review_queue", []) if item.get("post_id") != post_id]
    reviewed = list(state.get("reviewed_reports", []))
    reviewed.append(
        {
            "post_id": post_id,
            "action": action,
            "moderator_id": moderator_id,
            "reviewed_at": int(time.time()),
        }
    )
    state["review_queue"] = queue
    state["reviewed_reports"] = reviewed[-5000:]
    _save_state(state)
    return {"post_id": post_id, "action": action}


def get_moderation_summary():
    state = _load_state()
    auto_hidden = sum(1 for item in state.get("review_queue", []) if item.get("auto_hidden"))
    return {
        "reports_open": len(state.get("review_queue", [])),
        "reports_total": len(state.get("reports", [])),
        "auto_hidden_posts": auto_hidden,
        "shadow_banned_users": len(state.get("shadow_banned", [])),
        "blocked_phrase_count": len(BLOCKED_PHRASES),
    }
