from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.dependencies import require_internal_token
from app.models import PromoCode

router = APIRouter(prefix="/admin/promo")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/create")
def create_promo(
    code: str,
    max_uses: int,
    duration_days: int,
    free_year: bool = False,
    free_months: int = None,
    db: Session = Depends(get_db),
    _internal=Depends(require_internal_token),
):
    del _internal

    if max_uses <= 0 or duration_days <= 0 or (free_months is not None and free_months <= 0):
        raise HTTPException(status_code=400, detail="invalid_promo_limits")

    expires = datetime.utcnow() + timedelta(days=duration_days)

    promo = PromoCode(
        code=code,
        max_uses=max_uses,
        current_uses=0,
        free_year=free_year,
        free_months=free_months,
        starts_at=datetime.utcnow(),
        expires_at=expires
    )

    db.add(promo)
    db.commit()

    return {
        "status": "created",
        "code": code,
        "max_uses": max_uses,
        "expires_at": expires
    }
