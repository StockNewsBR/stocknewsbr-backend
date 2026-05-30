from __future__ import annotations

from datetime import datetime

from app.database import SessionLocal
from app.models import SocialComment
from app.social.db import ensure_social_tables
from app.social.moderation import can_publish


def _serialize_comment(comment: SocialComment) -> dict:
    return {
        "id": comment.id,
        "post_id": comment.post_id,
        "user_id": comment.user_id,
        "user": comment.display_name or f"user_{comment.user_id}",
        "user_email": comment.email,
        "user_avatar_url": comment.avatar_url,
        "text": comment.text,
        "image_url": comment.image_url,
        "timestamp": int((comment.created_at or datetime.utcnow()).timestamp()),
    }


def add_comment(post_id, user_id, text, image_url=None, display_name=None, email=None, avatar_url=None):
    ensure_social_tables()
    if post_id is None or not user_id or not text:
        return None

    allowed, reason = can_publish(int(user_id), str(text))

    if not allowed:
        return {
            "error": "comment_blocked",
            "reason": reason,
        }

    db = SessionLocal()

    try:
        comment = SocialComment(
            post_id=post_id,
            user_id=int(user_id),
            text=str(text)[:600],
            image_url=image_url,
            display_name=display_name or f"user_{user_id}",
            email=email,
            avatar_url=avatar_url,
        )
        db.add(comment)
        db.commit()
        db.refresh(comment)
        return _serialize_comment(comment)
    finally:
        db.close()


def get_comments(post_id, blocked_users=None):
    ensure_social_tables()
    blocked_users = set(blocked_users or [])
    db = SessionLocal()

    try:
        query = db.query(SocialComment).filter(SocialComment.post_id == post_id)

        if blocked_users:
            query = query.filter(~SocialComment.user_id.in_(blocked_users))

        rows = query.order_by(SocialComment.created_at.asc(), SocialComment.id.asc()).all()
        return [_serialize_comment(row) for row in rows]
    finally:
        db.close()


def get_comments_for_posts(post_ids, blocked_users=None):
    ensure_social_tables()
    lookup = list(dict.fromkeys(int(post_id) for post_id in (post_ids or []) if post_id is not None))

    if not lookup:
        return {}

    blocked_users = {int(user_id) for user_id in (blocked_users or []) if user_id is not None}
    db = SessionLocal()

    try:
        query = db.query(SocialComment).filter(SocialComment.post_id.in_(lookup))

        if blocked_users:
            query = query.filter(~SocialComment.user_id.in_(blocked_users))

        rows = query.order_by(
            SocialComment.post_id.asc(),
            SocialComment.created_at.asc(),
            SocialComment.id.asc(),
        ).all()

        grouped = {post_id: [] for post_id in lookup}
        for row in rows:
            grouped.setdefault(row.post_id, []).append(_serialize_comment(row))

        return grouped
    finally:
        db.close()


def count_comments(post_ids=None, post_id=None):
    ensure_social_tables()
    db = SessionLocal()

    try:
        query = db.query(SocialComment)

        if post_id is not None:
            return query.filter(SocialComment.post_id == post_id).count()

        if post_ids is not None:
            lookup = list(post_ids)
            if not lookup:
                return 0
            return query.filter(SocialComment.post_id.in_(lookup)).count()

        return query.count()
    finally:
        db.close()
