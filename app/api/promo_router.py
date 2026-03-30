from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import User
from app.security import get_current_user
from app.services.promo_codes import redeem_promo_code

router = APIRouter(prefix="/promo", tags=["Promo"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/redeem")
def redeem(
    code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return redeem_promo_code(db, current_user.id, code)
