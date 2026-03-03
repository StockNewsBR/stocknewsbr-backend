from fastapi import HTTPException
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import User


# =====================================================
# GET OR CREATE USER (Telegram Integration Ready)
# =====================================================

def get_or_create_user(db: Session, telegram_id: str):
    user = db.query(User).filter_by(telegram_id=telegram_id).first()

    if not user:
        trial_expiry = datetime.utcnow() + timedelta(days=90)

        user = User(
            telegram_id=telegram_id,
            plan="trial",
            trial_expires_at=trial_expiry,
            is_active=True,
            is_verified=True  # pode ajustar depois
        )

        db.add(user)
        db.commit()
        db.refresh(user)

    return user


# =====================================================
# REQUIRE VERIFIED
# =====================================================

def require_verified(user: User):
    if not user.is_verified:
        raise HTTPException(
            status_code=403,
            detail="verification_required"
        )


# =====================================================
# REQUIRE PREMIUM
# =====================================================

def require_premium(user: User):
    if user.plan not in ["trial", "premium"]:
        raise HTTPException(
            status_code=403,
            detail="premium_required"
        )


# =====================================================
# GET CURRENT USER
# (Session is injected externally - Professional Pattern)
# =====================================================

def get_current_user(db: Session):
    user = db.query(User).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return user