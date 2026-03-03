from datetime import datetime
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.auth import get_current_user


# =====================================================
# DATABASE SESSION (Single Session Per Request)
# =====================================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =====================================================
# TRIAL EXPIRATION CHECK
# =====================================================

def check_trial_expiration(user, db: Session):
    if user.plan == "trial" and user.trial_expires_at:
        if datetime.utcnow() > user.trial_expires_at:
            user.plan = "expired"
            db.commit()
            return False

    return True


# =====================================================
# REQUIRE ACTIVE PLAN (Enterprise Pattern)
# =====================================================

def require_active_plan(
    db: Session = Depends(get_db)
):
    # 🔹 Pega usuário usando a MESMA sessão
    current_user = get_current_user(db)

    # 🔹 Usuário inativo
    if not current_user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Usuário inativo"
        )

    # 🔹 Verifica expiração automática de trial
    trial_valid = check_trial_expiration(current_user, db)

    if not trial_valid:
        raise HTTPException(
            status_code=403,
            detail="Trial expirado. Faça upgrade para continuar."
        )

    # 🔹 Bloqueio manual de plano expirado
    if current_user.plan == "expired":
        raise HTTPException(
            status_code=403,
            detail="Plano expirado. Faça upgrade."
        )

    return current_user