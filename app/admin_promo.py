from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.database import SessionLocal
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
    db: Session = Depends(get_db)
):

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