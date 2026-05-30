from __future__ import annotations

from app.database import SessionLocal
from app.models import SocialFollow
from app.social.db import ensure_social_tables


def follow(user, target):
    ensure_social_tables()
    if not user or not target or int(user) == int(target):
        return {"status": "invalid"}

    db = SessionLocal()

    try:
        row = (
            db.query(SocialFollow)
            .filter(
                SocialFollow.user_id == int(user),
                SocialFollow.target_user_id == int(target),
            )
            .first()
        )

        if row:
            return {"status": "following"}

        row = SocialFollow(
            user_id=int(user),
            target_user_id=int(target),
        )
        db.add(row)
        db.commit()
        return {"status": "following"}
    finally:
        db.close()


def unfollow(user, target):
    ensure_social_tables()
    if not user or not target or int(user) == int(target):
        return {"status": "invalid"}

    db = SessionLocal()

    try:
        row = (
            db.query(SocialFollow)
            .filter(
                SocialFollow.user_id == int(user),
                SocialFollow.target_user_id == int(target),
            )
            .first()
        )

        if row is None:
            return {"status": "not_following"}

        db.delete(row)
        db.commit()
        return {"status": "unfollowed"}
    finally:
        db.close()


def is_following(user, target):
    ensure_social_tables()
    if not user or not target or int(user) == int(target):
        return False

    db = SessionLocal()

    try:
        row = (
            db.query(SocialFollow)
            .filter(
                SocialFollow.user_id == int(user),
                SocialFollow.target_user_id == int(target),
            )
            .first()
        )
        return row is not None
    finally:
        db.close()


def get_followers(user):
    ensure_social_tables()
    if not user:
        return []

    db = SessionLocal()

    try:
        rows = (
            db.query(SocialFollow.user_id)
            .filter(SocialFollow.target_user_id == int(user))
            .all()
        )
        return [row[0] for row in rows]
    finally:
        db.close()


def get_following_targets(user, targets):
    ensure_social_tables()
    if not user:
        return set()

    lookup = {int(target) for target in (targets or []) if target is not None}
    if not lookup:
        return set()

    db = SessionLocal()

    try:
        rows = (
            db.query(SocialFollow.target_user_id)
            .filter(
                SocialFollow.user_id == int(user),
                SocialFollow.target_user_id.in_(list(lookup)),
            )
            .all()
        )
        return {row[0] for row in rows}
    finally:
        db.close()
