import os
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import get_current_user, get_request_token, resolve_token_user
from app.services.access_service import _as_naive_utc, has_channel_access, refresh_user_access, utcnow

# Plans that unlock premium bundle fields (strategic panel, master score, AI tools, flow).
# Kept local to avoid importing plan constants across layers; mirrors access_service tiers.
_PREMIUM_PLANS = {"trial", "premium", "enterprise"}

LAST_ACCESS_WRITE_INTERVAL = timedelta(minutes=5)


def _should_update_last_access(user: User, now: datetime) -> bool:
    raw_last = getattr(user, "last_access_at", None)
    if raw_last is None or not isinstance(raw_last, datetime):
        return True
    last_access_at = _as_naive_utc(raw_last)
    if last_access_at is None:
        return True
    naive_now = _as_naive_utc(now) or utcnow()
    return naive_now - last_access_at >= LAST_ACCESS_WRITE_INTERVAL


def _refresh_and_touch_user_access(db: Session, user: User) -> tuple[bool, bool]:
    """Refreshes user entitlement state and updates activity timestamp with a 5-minute throttle.

    Performs DB commit only when an entitlement change occurs (e.g. trial expired) or
    when the activity write throttle allows it. Returns (access_changed, last_access_changed).
    """
    now = utcnow()

    before_state = (
        getattr(user, "is_active", None),
        getattr(user, "plan", None),
        getattr(user, "plan_status", None),
        getattr(user, "access_app", None),
        getattr(user, "access_web", None),
        getattr(user, "access_telegram", None),
    )

    refresh_user_access(user, touch_last_access=False)

    after_state = (
        getattr(user, "is_active", None),
        getattr(user, "plan", None),
        getattr(user, "plan_status", None),
        getattr(user, "access_app", None),
        getattr(user, "access_web", None),
        getattr(user, "access_telegram", None),
    )

    access_changed = before_state != after_state

    last_access_changed = False
    if _should_update_last_access(user, now):
        user.last_access_at = now
        last_access_changed = True

    if access_changed or last_access_changed:
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
        except Exception:
            db.rollback()
            raise

    return access_changed, last_access_changed


INSECURE_INTERNAL_API_TOKENS = frozenset(
    {
        "change_this_internal_token",
        "changeme",
        "change_me",
        "internal_token",
        "default",
    }
)
MIN_INTERNAL_API_TOKEN_LENGTH = 32


def _normalize_internal_api_token(value: str | None) -> str:
    token = str(value or "").strip()
    if token.lower() in INSECURE_INTERNAL_API_TOKENS or (token.startswith("<") and token.endswith(">")):
        return ""
    try:
        token.encode("ascii")
    except UnicodeEncodeError:
        return ""
    if len(token) < MIN_INTERNAL_API_TOKEN_LENGTH:
        return ""
    if len(set(token.lower())) <= 3:
        return ""
    return token


INTERNAL_API_TOKEN = _normalize_internal_api_token(os.getenv("INTERNAL_API_TOKEN"))


def require_active_plan(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _refresh_and_touch_user_access(db, current_user)

    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="user_inactive")

    if not has_channel_access(current_user):
        raise HTTPException(status_code=403, detail="subscription_required")

    return current_user


def resolve_premium_entitlement(
    token: str | None = Depends(get_request_token),
    db: Session = Depends(get_db),
) -> bool:
    """Optional, never-raising premium check for public endpoints.

    Returns True only when the request carries a valid token for a Trial/Pro plan.
    Anonymous requests, Básico/free plans, expired plans and invalid tokens all
    resolve to False so the public route keeps serving (gating decides what fields
    it may include, not whether it answers). Never raises -- a bad token must not
    turn a public 200 into a 401.
    """
    if not token:
        return False
    try:
        user = resolve_token_user(token, db, HTTPException(status_code=401, detail="x"))
        _refresh_and_touch_user_access(db, user)
        if not getattr(user, "is_active", True):
            return False
        return str(getattr(user, "plan", "") or "").lower() in _PREMIUM_PLANS
    except HTTPException as exc:
        if exc.status_code == 401:
            return False
        raise
    finally:
        # Public market routes can outlive this lookup while hydrating AI/news.
        # Return the connection before that work instead of pinning the pool.
        db.close()


def require_channel_access(channel: str):
    def _dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        _refresh_and_touch_user_access(db, current_user)

        if not current_user.is_active:
            raise HTTPException(status_code=403, detail="user_inactive")

        if not has_channel_access(current_user, channel):
            raise HTTPException(
                status_code=403,
                detail=f"{channel}_access_required",
            )

        return current_user

    return _dependency


def require_any_channel_access(*channels: str):
    valid_channels = tuple(channel for channel in channels if channel)

    def _dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        _refresh_and_touch_user_access(db, current_user)

        if not current_user.is_active:
            raise HTTPException(status_code=403, detail="user_inactive")

        if valid_channels and not any(has_channel_access(current_user, channel) for channel in valid_channels):
            detail = "_or_".join(valid_channels) if len(valid_channels) > 1 else valid_channels[0]
            raise HTTPException(
                status_code=403,
                detail=f"{detail}_access_required",
            )

        if not valid_channels and not has_channel_access(current_user):
            raise HTTPException(status_code=403, detail="subscription_required")

        return current_user

    return _dependency


def require_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
):
    configured_token = _normalize_internal_api_token(INTERNAL_API_TOKEN)
    if not configured_token:
        raise HTTPException(status_code=503, detail="internal_token_not_configured")

    if not isinstance(x_internal_token, str) or not x_internal_token:
        raise HTTPException(status_code=403, detail="internal_access_required")

    try:
        supplied_bytes = x_internal_token.encode("ascii")
        configured_bytes = configured_token.encode("ascii")
    except UnicodeEncodeError:
        raise HTTPException(status_code=403, detail="internal_access_required")

    if not secrets.compare_digest(supplied_bytes, configured_bytes):
        raise HTTPException(status_code=403, detail="internal_access_required")

    return True
