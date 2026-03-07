from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.promo_codes import redeem_promo_code

router = APIRouter(prefix="/promo", tags=["Promo"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/redeem")
def redeem(code: str, user_id: int, db: Session = Depends(get_db)):
    return redeem_promo_code(db, user_id, code)