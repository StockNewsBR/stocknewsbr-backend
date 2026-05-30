from __future__ import annotations

from sqlalchemy import func

from app.database import SessionLocal
from app.models import SocialLike
from app.social.db import ensure_social_tables


def like_post(post_id: int, user_id: int) -> int:
    ensure_social_tables()
    db = SessionLocal()

    try:
        row = (
            db.query(SocialLike)
            .filter(
                SocialLike.post_id == int(post_id),
                SocialLike.user_id == int(user_id),
            )
            .first()
        )

        if row is None:
            db.add(SocialLike(post_id=int(post_id), user_id=int(user_id)))
            db.commit()

        return count_likes(post_id)
    finally:
        db.close()


def unlike_post(post_id: int, user_id: int) -> int:
    ensure_social_tables()
    db = SessionLocal()

    try:
        row = (
            db.query(SocialLike)
            .filter(
                SocialLike.post_id == int(post_id),
                SocialLike.user_id == int(user_id),
            )
            .first()
        )

        if row is not None:
            db.delete(row)
            db.commit()

        return count_likes(post_id)
    finally:
        db.close()


def count_likes(post_id: int) -> int:
    ensure_social_tables()
    db = SessionLocal()

    try:
        return (
            db.query(SocialLike)
            .filter(SocialLike.post_id == int(post_id))
            .count()
        )
    finally:
        db.close()


def get_like_counts(post_ids):
    ensure_social_tables()
    lookup = list(dict.fromkeys(int(post_id) for post_id in (post_ids or []) if post_id is not None))

    if not lookup:
        return {}

    db = SessionLocal()

    try:
        rows = (
            db.query(SocialLike.post_id, func.count(SocialLike.id))
            .filter(SocialLike.post_id.in_(lookup))
            .group_by(SocialLike.post_id)
            .all()
        )
        return {int(post_id): int(total or 0) for post_id, total in rows}
    finally:
        db.close()


def has_liked(post_id: int, user_id: int) -> bool:
    ensure_social_tables()
    db = SessionLocal()

    try:
        return (
            db.query(SocialLike)
            .filter(
                SocialLike.post_id == int(post_id),
                SocialLike.user_id == int(user_id),
            )
            .first()
            is not None
        )
    finally:
        db.close()


def get_liked_post_ids(post_ids, user_id: int):
    ensure_social_tables()
    lookup = list(dict.fromkeys(int(post_id) for post_id in (post_ids or []) if post_id is not None))

    if not lookup or not user_id:
        return set()

    db = SessionLocal()

    try:
        rows = (
            db.query(SocialLike.post_id)
            .filter(
                SocialLike.user_id == int(user_id),
                SocialLike.post_id.in_(lookup),
            )
            .all()
        )
        return {int(post_id) for (post_id,) in rows}
    finally:
        db.close()
