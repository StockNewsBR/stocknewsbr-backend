# =====================================================
# MODERATION ENGINE (ADVANCED SAFE VERSION)
# =====================================================

import json
import os
import threading
import time
from pathlib import Path

from app.core.atomic_io import interprocess_file_lock, read_json_file, write_json_file_atomic
from app.social.guardian import SocialGuardian
from app.system.system_metrics import increment_reports


MODERATION_STORE_PATH = Path(os.getenv("MODERATION_STORE_PATH", "data/moderation_state.json"))
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
        "guardian_audit": [],
        "guardian_scores": {},
    }


def _load_state():
    with _lock:
        if not MODERATION_STORE_PATH.exists():
            return _default_state()

        data = read_json_file(MODERATION_STORE_PATH, _default_state)

        base = _default_state()
        base.update(data if isinstance(data, dict) else {})
        return base


def _save_state(state):
    with _lock:
        write_json_file_atomic(MODERATION_STORE_PATH, state, ensure_ascii=True)


def _mutate_state(mutator):
    # Mission 31F: lock interprocesso ANTES do _lock (ordering fixo). Sem ele,
    # read-modify-write concorrente entre processos perde atualizações; o
    # ordering evita deadlock com quem só usa _lock (nunca o inverso).
    with interprocess_file_lock(MODERATION_STORE_PATH.with_suffix(".json.lock")):
        with _lock:
            state = _load_state()
            result = mutator(state)
            _save_state(state)
            return result


def mute(user_id, target):
    if not user_id or not target:
        return False

    def mutator(state):
        muted = state.setdefault("muted", {})
        muted.setdefault(str(user_id), [])

        if target not in muted[str(user_id)]:
            muted[str(user_id)].append(target)
        return True

    return _mutate_state(mutator)


def block(user_id, target):
    if not user_id or not target:
        return False

    def mutator(state):
        blocked = state.setdefault("blocked", {})
        blocked.setdefault(str(user_id), [])

        if target not in blocked[str(user_id)]:
            blocked[str(user_id)].append(target)
        return True

    return _mutate_state(mutator)


def get_blocked_users(user_id):
    if not user_id:
        return set()

    state = _load_state()
    blocked = state.get("blocked", {})
    return set(blocked.get(str(user_id), []))


def _flag_reasons(text: str):
    text = (text or "").lower()
    return [phrase for phrase in BLOCKED_PHRASES if phrase in text]


def _score_record(state, user_id):
    scores = state.setdefault("guardian_scores", {})
    key = str(user_id)
    record = dict(scores.get(key) or {})
    record.setdefault("user_id", int(user_id))
    record.setdefault("score", SocialGuardian.TRUST_START)
    record.setdefault("label", SocialGuardian.trust_label(record.get("score")))
    record.setdefault("approved_posts", 0)
    record.setdefault("approved_interactions", 0)
    record.setdefault("reports_received", 0)
    record.setdefault("removed_posts", 0)
    record.setdefault("updated_at", int(time.time()))
    scores[key] = record
    return record


def _adjust_score(state, user_id, delta, *, approved_content_type=None, report=False, removed=False):
    if not user_id:
        return None
    record = _score_record(state, user_id)
    record["score"] = SocialGuardian.clamp_score(int(record.get("score") or SocialGuardian.TRUST_START) + int(delta or 0))
    record["label"] = SocialGuardian.trust_label(record["score"])
    record["updated_at"] = int(time.time())
    if approved_content_type == "post":
        record["approved_posts"] = int(record.get("approved_posts") or 0) + 1
    elif approved_content_type:
        record["approved_interactions"] = int(record.get("approved_interactions") or 0) + 1
    if report:
        record["reports_received"] = int(record.get("reports_received") or 0) + 1
    if removed:
        record["removed_posts"] = int(record.get("removed_posts") or 0) + 1
    return record


def _append_audit(state, action, *, actor_user_id=None, target_user_id=None, post_id=None, content_type=None, reason=None, details=None):
    audit = state.setdefault("guardian_audit", [])
    audit.append(
        {
            "action": action,
            "actor_user_id": actor_user_id,
            "target_user_id": target_user_id,
            "post_id": post_id,
            "content_type": content_type,
            "reason": reason,
            "details": details or {},
            "timestamp": int(time.time()),
        }
    )
    state["guardian_audit"] = audit[-20000:]


def can_publish(user_id: int, text: str):
    if not user_id:
        return False, "invalid_user"

    guardian_decision = SocialGuardian.validate_content(text)

    flagged_phrases = _flag_reasons(text)

    now = int(time.time())

    def mutator(state):
        if user_id in state.get("shadow_banned", []):
            return False, "user_shadow_banned"

        if not guardian_decision.allowed:
            _append_audit(
                state,
                "content_blocked",
                actor_user_id=user_id,
                content_type="text",
                reason=guardian_decision.reason,
                details={
                    "category": guardian_decision.category,
                    "matched_terms": list(guardian_decision.matched_terms),
                },
            )
            return False, guardian_decision.reason

        if flagged_phrases:
            _append_audit(
                state,
                "content_blocked",
                actor_user_id=user_id,
                content_type="text",
                reason="blocked_phrase_detected",
                details={"matched_terms": flagged_phrases},
            )
            return False, "blocked_phrase_detected"

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
        return True, "allowed"

    return _mutate_state(mutator)


def validate_attachment_url(user_id: int, image_url: str | None):
    decision = SocialGuardian.validate_attachment_url(image_url)
    if decision.allowed:
        return True, "allowed"

    def mutator(state):
        _append_audit(
            state,
            "content_blocked",
            actor_user_id=user_id,
            content_type="attachment",
            reason=decision.reason,
            details={
                "category": decision.category,
                "matched_terms": list(decision.matched_terms),
            },
        )
        return False, decision.reason

    return _mutate_state(mutator)


def record_content_approved(user_id, *, content_type: str, content_id=None, post_id=None, ticker=None):
    if not user_id:
        return None

    def mutator(state):
        record = _adjust_score(
            state,
            int(user_id),
            SocialGuardian.approved_delta(content_type),
            approved_content_type=content_type,
        )
        audit_action = "post_created" if content_type == "post" else f"{content_type}_created"
        _append_audit(
            state,
            audit_action,
            actor_user_id=int(user_id),
            target_user_id=int(user_id),
            post_id=post_id or content_id,
            content_type=content_type,
            reason="approved",
            details={"ticker": ticker, "content_id": content_id},
        )
        return record

    return _mutate_state(mutator)


def record_post_removed(post_id, *, actor_user_id=None, target_user_id=None, reason: str | None = None):
    def mutator(state):
        if target_user_id:
            _adjust_score(
                state,
                int(target_user_id),
                SocialGuardian.REMOVED_POST_DELTA,
                removed=True,
            )
        _append_audit(
            state,
            "post_removed",
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            post_id=post_id,
            content_type="post",
            reason=reason or "removed",
        )

    return _mutate_state(mutator)


def report(user_id, post_id, reason: str | None = None, reporter_note: str | None = None, target_user_id: int | None = None):
    if not user_id or post_id is None:
        return False

    normalized_reason = SocialGuardian.normalize_report_reason(reason)

    # Mission 31F: todo o read-modify-write roda dentro de _mutate_state; o
    # padrão anterior (_load_state ... _save_state) perdia reports concorrentes
    # registrados entre a leitura e a gravação.
    def mutator(state):
        reports = state.setdefault("reports", [])
        queue = state.setdefault("review_queue", [])

        report_item = {
            "id": f"report-{int(time.time() * 1000)}-{user_id}",
            "user": user_id,
            "post": post_id,
            "reason": normalized_reason,
            "reason_label": SocialGuardian.REPORT_REASONS.get(normalized_reason, "Outro"),
            "note": reporter_note,
            "target_user_id": target_user_id,
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
            "last_reason_label": report_item["reason_label"],
            "target_user_id": target_user_id,
            "updated_at": int(time.time()),
        }

        queue = [item for item in queue if item.get("post_id") != post_id]
        queue.append(queue_item)

        state["reports"] = reports[-20000:]
        state["review_queue"] = queue[-5000:]
        if target_user_id:
            _adjust_score(
                state,
                int(target_user_id),
                SocialGuardian.REPORT_DELTA,
                report=True,
            )
        _append_audit(
            state,
            "post_reported",
            actor_user_id=user_id,
            target_user_id=target_user_id,
            post_id=post_id,
            content_type="post",
            reason=normalized_reason,
            details={"reason_label": report_item["reason_label"], "note": reporter_note},
        )
        if target_user_id:
            _append_audit(
                state,
                "user_reported",
                actor_user_id=user_id,
                target_user_id=target_user_id,
                post_id=post_id,
                content_type="user",
                reason=normalized_reason,
            )
        return True

    return _mutate_state(mutator)


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
    # Mission 31F: read-modify-write atômico via _mutate_state; o padrão
    # anterior podia perder atualização concorrente (novo report ou outra
    # revisão) entre a leitura e a gravação.
    def mutator(state):
        existing_item = next((item for item in state.get("review_queue", []) if item.get("post_id") == post_id), {})
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
        if str(action).lower() in {"hide", "remove"}:
            target_user_id = existing_item.get("target_user_id")
            if target_user_id:
                _adjust_score(state, int(target_user_id), SocialGuardian.REMOVED_POST_DELTA, removed=True)
            _append_audit(
                state,
                "post_removed",
                actor_user_id=moderator_id,
                target_user_id=target_user_id,
                post_id=post_id,
                content_type="post",
                reason=str(action).lower(),
            )
        return {"post_id": post_id, "action": action}

    return _mutate_state(mutator)


def get_user_guardian_score(user_id):
    if not user_id:
        return {
            "score": SocialGuardian.TRUST_START,
            "label": SocialGuardian.trust_label(SocialGuardian.TRUST_START),
        }
    state = _load_state()
    record = _score_record(state, int(user_id))
    return {
        **record,
        "score": SocialGuardian.clamp_score(record.get("score")),
        "label": SocialGuardian.trust_label(record.get("score")),
    }


def get_guardian_audit(limit: int = 100):
    state = _load_state()
    items = list(state.get("guardian_audit", []))
    return items[-max(1, min(int(limit or 100), 500)) :]


def get_moderation_summary():
    state = _load_state()
    auto_hidden = sum(1 for item in state.get("review_queue", []) if item.get("auto_hidden"))
    return {
        "reports_open": len(state.get("review_queue", [])),
        "reports_total": len(state.get("reports", [])),
        "auto_hidden_posts": auto_hidden,
        "shadow_banned_users": len(state.get("shadow_banned", [])),
        "blocked_phrase_count": len(BLOCKED_PHRASES),
        "social_guardian": {
            "audit_events": len(state.get("guardian_audit", [])),
            "trusted_users": len(state.get("guardian_scores", {})),
            "blocked_categories": SocialGuardian.blocked_terms(),
            "report_reasons": SocialGuardian.REPORT_REASONS,
        },
    }
