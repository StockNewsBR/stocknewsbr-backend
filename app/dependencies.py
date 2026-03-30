import os
import secrets

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import get_current_user
from app.services.access_service import has_channel_access, refresh_user_access

INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "").strip()


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
    if not INTERNAL_API_TOKEN:
        raise HTTPException(status_code=503, detail="internal_token_not_configured")

    if not x_internal_token or not secrets.compare_digest(x_internal_token, INTERNAL_API_TOKEN):
        raise HTTPException(status_code=403, detail="internal_access_required")

    return True
