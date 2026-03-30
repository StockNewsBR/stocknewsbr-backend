# =====================================================
# STOCKNEWSBR USER SERVICES
# =====================================================

import secrets

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import User
from app.security import hash_password
from app.services.access_service import (
    accept_legal_documents,
    ensure_referral_code,
    grant_trial_access,
    link_telegram_account,
    refresh_user_access,
)


def get_or_create_user(db: Session, telegram_id: str, telegram_username: str | None = None):
    user = db.query(User).filter(User.telegram_id == telegram_id).first()

    if user:
        refresh_user_access(user)
        return user

    pseudo_email = f"telegram_{telegram_id}@stocknewsbr.local"

    user = User(
        email=pseudo_email,
        password_hash=hash_password(secrets.token_hex(24)),
        display_name=telegram_username or f"telegram_{telegram_id}",
        is_active=True,
        is_verified=True,
        referral_code=secrets.token_hex(4).upper(),
    )

    grant_trial_access(user)
    accept_legal_documents(user, True, True, True)

    db.add(user)
    db.flush()
    ensure_referral_code(db, user)
    link_telegram_account(db, user, telegram_id, telegram_username)
    db.commit()
    db.refresh(user)

    return user


def require_verified(user: User):
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="verification_required")


def require_premium(user: User):
    refresh_user_access(user)

    if user.plan not in ["trial", "premium", "enterprise"]:
        raise HTTPException(status_code=403, detail="premium_required")
