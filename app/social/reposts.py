from __future__ import annotations

from datetime import datetime

from sqlalchemy import func

from app.database import SessionLocal
from app.models import SocialRepost
from app.social.db import ensure_social_tables
from app.social.moderation import can_publish


def _normalize_quote_text(text: str | None) -> str | None:
    value = (text or "").strip()
    if not value:
        return None
    return value[:600]


def create_repost(post_id, user_id, quote_text=None):
    ensure_social_tables()

    if post_id is None or not user_id:
        return None

    allowed, reason = can_publish(int(user_id), _normalize_quote_text(quote_text) or "repost")
    if not allowed:
        return {
            "error": "repost_blocked",
            "reason": reason,
        }

    db = SessionLocal()

    try:
        row = (
            db.query(SocialRepost)
            .filter(
                SocialRepost.post_id == int(post_id),
                SocialRepost.user_id == int(user_id),
            )
            .first()
        )

        if row is None:
            row = SocialRepost(
                post_id=int(post_id),
                user_id=int(user_id),
                quote_text=_normalize_quote_text(quote_text),
            )
            db.add(row)
            db.commit()
            db.refresh(row)

        return serialize_repost(row)
    finally:
        db.close()


def delete_repost(post_id, user_id):
    ensure_social_tables()

    if post_id is None or not user_id:
        return False

    db = SessionLocal()

    try:
        row = (
            db.query(SocialRepost)
            .filter(
                SocialRepost.post_id == int(post_id),
                SocialRepost.user_id == int(user_id),
            )
            .first()
        )

        if row is None:
            return False

        db.delete(row)
        db.commit()
        return True
    finally:
        db.close()


def count_reposts(post_id: int) -> int:
    ensure_social_tables()
    db = SessionLocal()

    try:
        return (
            db.query(SocialRepost)
            .filter(SocialRepost.post_id == int(post_id))
            .count()
        )
    finally:
        db.close()


def get_repost_counts(post_ids):
    ensure_social_tables()
    lookup = list(dict.fromkeys(int(post_id) for post_id in (post_ids or []) if post_id is not None))

    if not lookup:
        return {}

    db = SessionLocal()

    try:
        rows = (
            db.query(SocialRepost.post_id, func.count(SocialRepost.id))
            .filter(SocialRepost.post_id.in_(lookup))
            .group_by(SocialRepost.post_id)
            .all()
        )
        return {int(post_id): int(total or 0) for post_id, total in rows}
    finally:
        db.close()


def has_reposted(post_id: int, user_id: int) -> bool:
    ensure_social_tables()
    db = SessionLocal()

    try:
        return (
            db.query(SocialRepost)
            .filter(
                SocialRepost.post_id == int(post_id),
                SocialRepost.user_id == int(user_id),
            )
            .first()
            is not None
        )
    finally:
        db.close()


def get_reposted_post_ids(post_ids, user_id: int):
    ensure_social_tables()
    lookup = list(dict.fromkeys(int(post_id) for post_id in (post_ids or []) if post_id is not None))

    if not lookup or not user_id:
        return set()

    db = SessionLocal()

    try:
        rows = (
            db.query(SocialRepost.post_id)
            .filter(
                SocialRepost.user_id == int(user_id),
                SocialRepost.post_id.in_(lookup),
            )
            .all()
        )
        return {int(post_id) for (post_id,) in rows}
    finally:
        db.close()


def get_user_reposts_for_posts(post_ids, user_id: int):
    ensure_social_tables()
    lookup = list(dict.fromkeys(int(post_id) for post_id in (post_ids or []) if post_id is not None))

    if not lookup or not user_id:
        return {}

    db = SessionLocal()

    try:
        rows = (
            db.query(SocialRepost)
            .filter(
                SocialRepost.user_id == int(user_id),
                SocialRepost.post_id.in_(lookup),
            )
            .all()
        )
        return {int(row.post_id): serialize_repost(row) for row in rows}
    finally:
        db.close()


def get_user_repost(post_id: int, user_id: int) -> dict | None:
    ensure_social_tables()
    db = SessionLocal()

    try:
        row = (
            db.query(SocialRepost)
            .filter(
                SocialRepost.post_id == int(post_id),
                SocialRepost.user_id == int(user_id),
            )
            .first()
        )
        if row is None:
            return None
        return serialize_repost(row)
    finally:
        db.close()


def serialize_repost(repost: SocialRepost) -> dict:
    return {
        "id": repost.id,
        "post_id": repost.post_id,
        "user_id": repost.user_id,
        "quote_text": repost.quote_text,
        "timestamp": int((repost.created_at or datetime.utcnow()).timestamp()),
    }
