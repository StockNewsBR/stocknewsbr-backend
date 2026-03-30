import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.ai_market_pulse import market_pulse
from app.cache.snapshot_cache import get_snapshot_signals
from app.database import get_db
from app.dependencies import require_internal_token
from app.models import User
from app.services.access_service import has_channel_access, refresh_user_access
from app.services.auth_session_service import consume_telegram_link_token

logger = logging.getLogger("stocknewsbr.internal")

router = APIRouter(
    prefix="/internal",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


class TelegramLinkConsumePayload(BaseModel):
    link_code: str = Field(..., min_length=6, max_length=64)
    telegram_id: str = Field(..., min_length=3, max_length=64)
    telegram_username: str | None = Field(default=None, max_length=64)


@router.get("/opportunities")
def internal_opportunities(limit: int = 10):
    signals = get_snapshot_signals(limit=max(1, min(limit, 50)))
    return {
        "count": len(signals),
        "signals": signals,
    }


@router.get("/market-pulse")
def internal_market_pulse():
    return market_pulse(get_snapshot_signals(limit=200))


@router.get("/telegram/access/{telegram_id}")
def telegram_access(
    telegram_id: str,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.telegram_id == str(telegram_id)).first()

    if not user:
        return {
            "allowed": False,
            "linked": False,
            "reason": "telegram_not_linked",
        }

    refresh_user_access(user)
    db.add(user)
    db.commit()
    db.refresh(user)
    allowed = has_channel_access(user, "telegram")

    return {
        "allowed": allowed,
        "linked": True,
        "plan": user.plan,
        "plan_status": user.plan_status,
        "telegram_username": user.telegram_username,
        "reason": None if allowed else "telegram_access_required",
    }


@router.post("/telegram/link/consume")
def telegram_link_consume(
    payload: TelegramLinkConsumePayload,
    db: Session = Depends(get_db),
):
    try:
        user, token = consume_telegram_link_token(
            db,
            link_code=payload.link_code,
            telegram_id=payload.telegram_id,
            telegram_username=payload.telegram_username,
        )
    except ValueError as exc:
        return {
            "ok": False,
            "detail": str(exc),
        }

    db.commit()
    db.refresh(user)
    return {
        "ok": True,
        "email": user.email,
        "plan": user.plan,
        "plan_status": user.plan_status,
        "telegram_username": user.telegram_username,
        "origin_channel": token.origin_channel,
    }
