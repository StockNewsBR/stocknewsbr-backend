from __future__ import annotations

from app.database import SessionLocal
from app.models import SocialComment, SocialLike, SocialPost, SocialRepost
from app.services.symbol_registry import canonical_symbol
from app.social.db import ensure_social_tables, utc_social_datetime
from app.social.moderation import (
    can_publish,
    get_hidden_post_ids,
    get_user_guardian_score,
    get_user_guardian_scores,
    is_post_hidden,
    record_content_approved,
    record_post_removed,
    validate_attachment_url,
)


def _serialize_post(post: SocialPost, guardian_score: dict | None = None) -> dict:
    if guardian_score is None:
        guardian_score = get_user_guardian_score(post.user_id)
    created_at = utc_social_datetime(post.created_at)
    return {
        "id": post.id,
        "user_id": post.user_id,
        "user": _public_name(post.display_name),
        "user_avatar_url": post.avatar_url,
        "text": post.text,
        "ticker": canonical_symbol(post.ticker) or None,
        "image_url": post.image_url,
        "sentiment": post.sentiment,
        "timestamp": int(created_at.timestamp()) if created_at else None,
        "created_at": created_at.isoformat().replace("+00:00", "Z") if created_at else None,
        "social_guardian_score": guardian_score.get("score"),
        "social_guardian_label": guardian_score.get("label"),
    }


def _public_name(value) -> str:
    name = str(value or "").strip()
    return name if name and "@" not in name and not name.lower().startswith("user_") else "Trader"


def create_post(
    user_id,
    text,
    ticker=None,
    image_url=None,
    sentiment=None,
    display_name=None,
    email=None,
    avatar_url=None,
):
    ensure_social_tables()

    normalized_text = str(text or "").strip()
    if not user_id or (not normalized_text and not image_url):
        return None

    resolved_user_id = int(user_id)
    allowed, reason = can_publish(resolved_user_id, normalized_text)

    if not allowed:
        return {
            "error": "post_blocked",
            "reason": reason,
        }

    attachment_allowed, attachment_reason = validate_attachment_url(resolved_user_id, image_url)
    if not attachment_allowed:
        return {
            "error": "post_blocked",
            "reason": attachment_reason,
        }

    db = SessionLocal()

    try:
        normalized_ticker = canonical_symbol(ticker) or None
        post = SocialPost(
            user_id=resolved_user_id,
            ticker=normalized_ticker,
            text=normalized_text[:1000],
            image_url=image_url,
            sentiment=sentiment,
            display_name=_public_name(display_name),
            email=email,
            avatar_url=avatar_url,
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        record_content_approved(
            resolved_user_id,
            content_type="post",
            content_id=post.id,
            post_id=post.id,
            ticker=normalized_ticker,
        )
        return _serialize_post(post)
    finally:
        db.close()


def get_posts(ticker=None, limit=50, blocked_users=None):
    ensure_social_tables()
    blocked_users = set(blocked_users or [])
    normalized_ticker = canonical_symbol(ticker) or None
    db = SessionLocal()

    try:
        query = db.query(SocialPost)

        if normalized_ticker:
            query = query.filter(SocialPost.ticker == normalized_ticker)

        if blocked_users:
            query = query.filter(~SocialPost.user_id.in_(blocked_users))

        rows = (
            query.order_by(SocialPost.created_at.desc(), SocialPost.id.desc())
            .limit(max(1, min(int(limit or 50), 500)))
            .all()
        )

        # Missão 34: lote — 2 leituras do estado de moderação por request em
        # vez de 2 por post (N+1 de I/O + parse JSON com N até 500).
        guardian_scores = get_user_guardian_scores(row.user_id for row in rows)
        serialized = [
            _serialize_post(row, guardian_score=dict(guardian_scores[row.user_id]))
            for row in rows
        ]
        hidden_post_ids = get_hidden_post_ids(row.get("id") for row in serialized)
        return [row for row in serialized if row.get("id") not in hidden_post_ids]
    finally:
        db.close()


def count_posts(ticker=None):
    ensure_social_tables()
    db = SessionLocal()

    try:
        query = db.query(SocialPost)

        if ticker:
            query = query.filter(SocialPost.ticker == canonical_symbol(ticker))

        return query.count()
    finally:
        db.close()


def get_post(post_id):
    ensure_social_tables()
    db = SessionLocal()

    try:
        post = db.query(SocialPost).filter(SocialPost.id == post_id).first()

        if not post:
            return None

        if is_post_hidden(post.id):
            return None

        return _serialize_post(post)
    finally:
        db.close()


def get_post_ticker(post_id):
    post = get_post(post_id)
    if not post:
        return None
    return post.get("ticker")


def delete_post(post_id, user_id=None, *, can_moderate=False):
    ensure_social_tables()
    db = SessionLocal()

    try:
        post = db.query(SocialPost).filter(SocialPost.id == post_id).first()

        if not post:
            return False

        # Fail closed on the caller's identity. The previous form skipped the
        # ownership comparison entirely when `user_id` was None, so any caller
        # that forgot to pass the acting user deleted arbitrary posts. Deleting
        # someone else's post now requires either being its owner or holding an
        # explicit moderation grant -- an absent identity is never enough.
        if not can_moderate and (user_id is None or post.user_id != user_id):
            return False

        target_user_id = post.user_id
        db.query(SocialComment).filter(SocialComment.post_id == post.id).delete(synchronize_session=False)
        db.query(SocialLike).filter(SocialLike.post_id == post.id).delete(synchronize_session=False)
        db.query(SocialRepost).filter(SocialRepost.post_id == post.id).delete(synchronize_session=False)
        db.delete(post)
        db.commit()
        record_post_removed(post_id, actor_user_id=user_id, target_user_id=target_user_id, reason="deleted")
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
