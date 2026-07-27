import os
import secrets

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import get_current_user, get_request_token, resolve_token_user
from app.services.access_service import has_channel_access, refresh_user_access

# Plans that unlock premium bundle fields (strategic panel, master score, AI tools, flow).
# Kept local to avoid importing plan constants across layers; mirrors access_service tiers.
_PREMIUM_PLANS = {"trial", "premium", "enterprise"}

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
    refresh_user_access(current_user)

    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="user_inactive")

    if not has_channel_access(current_user):
        db.add(current_user)
        db.commit()
        raise HTTPException(status_code=403, detail="subscription_required")

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
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
        refresh_user_access(user)
        return str(getattr(user, "plan", "") or "").lower() in _PREMIUM_PLANS
    except Exception:
        return False


def require_channel_access(channel: str):
    def _dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        refresh_user_access(current_user)

        if not current_user.is_active:
            db.add(current_user)
            db.commit()
            raise HTTPException(status_code=403, detail="user_inactive")

        if not has_channel_access(current_user, channel):
            db.add(current_user)
            db.commit()
            raise HTTPException(
                status_code=403,
                detail=f"{channel}_access_required",
            )

        db.add(current_user)
        db.commit()
        db.refresh(current_user)
        return current_user

    return _dependency


def require_any_channel_access(*channels: str):
    valid_channels = tuple(channel for channel in channels if channel)

    def _dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        refresh_user_access(current_user)

        if not current_user.is_active:
            db.add(current_user)
            db.commit()
            raise HTTPException(status_code=403, detail="user_inactive")

        if valid_channels and not any(has_channel_access(current_user, channel) for channel in valid_channels):
            db.add(current_user)
            db.commit()
            detail = "_or_".join(valid_channels) if len(valid_channels) > 1 else valid_channels[0]
            raise HTTPException(
                status_code=403,
                detail=f"{detail}_access_required",
            )

        if not valid_channels and not has_channel_access(current_user):
            db.add(current_user)
            db.commit()
            raise HTTPException(status_code=403, detail="subscription_required")

        db.add(current_user)
        db.commit()
        db.refresh(current_user)
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
