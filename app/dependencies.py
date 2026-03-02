from app.database import SessionLocal
from datetime import datetime
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from app.auth import get_current_user


# ==============================
# DATABASE SESSION
# ==============================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==============================
# TRIAL CHECK LOGIC
# ==============================

def check_trial_expiration(user, db: Session):
    if user.plan == "trial" and user.trial_expires_at:
        if datetime.utcnow() > user.trial_expires_at:
            user.plan = "expired"
            db.commit()
            return False

    return True


# ==============================
# MAIN PLAN VALIDATION
# ==============================

def require_active_plan(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Usuário inativo
    if not current_user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Usuário inativo"
        )

    # Verifica expiração de trial
    trial_valid = check_trial_expiration(current_user, db)

    if not trial_valid:
        raise HTTPException(
            status_code=403,
            detail="Trial expirado. Faça upgrade para continuar."
        )

    # Bloqueia plano expirado manualmente
    if current_user.plan == "expired":
        raise HTTPException(
            status_code=403,
            detail="Plano expirado. Faça upgrade."
        )

    return current_user