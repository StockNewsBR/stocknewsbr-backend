from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.promo_codes import redeem_promo_code

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/promo/redeem")
def redeem(code: str, user_id: int, db: Session = Depends(get_db)):

    return redeem_promo_code(db, user_id, code)