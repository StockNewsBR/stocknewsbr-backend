from __future__ import annotations

from datetime import datetime

from app.database import SessionLocal
from app.models import SocialPost
from app.services.symbol_registry import canonical_symbol
from app.social.db import ensure_social_tables
from app.social.moderation import (
    can_publish,
    get_user_guardian_score,
    is_post_hidden,
    record_content_approved,
    record_post_removed,
    validate_attachment_url,
)


def _serialize_post(post: SocialPost) -> dict:
    guardian_score = get_user_guardian_score(post.user_id)
    return {
        "id": post.id,
        "user_id": post.user_id,
        "user": post.display_name or f"user_{post.user_id}",
        "user_email": post.email,
        "user_avatar_url": post.avatar_url,
        "text": post.text,
        "ticker": canonical_symbol(post.ticker) or None,
        "image_url": post.image_url,
        "sentiment": post.sentiment,
        "timestamp": int((post.created_at or datetime.utcnow()).timestamp()),
        "social_guardian_score": guardian_score.get("score"),
        "social_guardian_label": guardian_score.get("label"),
    }


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

    if not user_id or not text:
        return None

    resolved_user_id = int(user_id)
    allowed, reason = can_publish(resolved_user_id, str(text))

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
            text=str(text)[:1000],
            image_url=image_url,
            sentiment=sentiment,
            display_name=display_name or f"user_{user_id}",
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

        serialized = [_serialize_post(row) for row in reversed(rows)]
        return [row for row in serialized if not is_post_hidden(row.get("id"))]
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


def delete_post(post_id, user_id=None):
    ensure_social_tables()
    db = SessionLocal()

    try:
        post = db.query(SocialPost).filter(SocialPost.id == post_id).first()

        if not post:
            return False

        if user_id is not None and post.user_id != user_id:
            return False

        target_user_id = post.user_id
        db.delete(post)
        db.commit()
        record_post_removed(post_id, actor_user_id=user_id, target_user_id=target_user_id, reason="deleted")
        return True
    finally:
        db.close()
