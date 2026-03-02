from fastapi import HTTPException
from datetime import datetime, timedelta
from app.models import User


def get_or_create_user(db, telegram_id: str):
    user = db.query(User).filter_by(telegram_id=telegram_id).first()

    if not user:
        trial_expiry = datetime.utcnow() + timedelta(days=90)
        user = User(
            telegram_id=telegram_id,
            plan="trial",
            trial_expires_at=trial_expiry
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return user


def require_verified(user):
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="verification_required")


def require_premium(user):
    if user.plan not in ["trial", "premium"]:
        raise HTTPException(status_code=403, detail="premium_required")

# ==============================
# GET CURRENT USER (FIX DEPLOY)
# ==============================

from fastapi import Depends
from sqlalchemy.orm import Session
from app.database import SessionLocal

def get_current_user(db: Session = Depends(SessionLocal)):
    user = db.query(User).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user