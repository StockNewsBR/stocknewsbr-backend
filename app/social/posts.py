from __future__ import annotations

from datetime import datetime

from app.database import SessionLocal
from app.models import SocialPost
from app.social.db import ensure_social_tables
from app.social.moderation import can_publish, is_post_hidden


def _serialize_post(post: SocialPost) -> dict:
    return {
        "id": post.id,
        "user_id": post.user_id,
        "user": post.display_name or f"user_{post.user_id}",
        "user_email": post.email,
        "user_avatar_url": post.avatar_url,
        "text": post.text,
        "ticker": (post.ticker or "").upper() or None,
        "image_url": post.image_url,
        "sentiment": post.sentiment,
        "timestamp": int((post.created_at or datetime.utcnow()).timestamp()),
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

    allowed, reason = can_publish(int(user_id), str(text))

    if not allowed:
        return {
            "error": "post_blocked",
            "reason": reason,
        }

    db = SessionLocal()

    try:
        post = SocialPost(
            user_id=int(user_id),
            ticker=(ticker or "").upper() or None,
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
        return _serialize_post(post)
    finally:
        db.close()


def get_posts(ticker=None, limit=50, blocked_users=None):
    ensure_social_tables()
    blocked_users = set(blocked_users or [])
    normalized_ticker = (ticker or "").upper() or None
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
            query = query.filter(SocialPost.ticker == str(ticker).upper())

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

        db.delete(post)
        db.commit()
        return True
    finally:
        db.close()
