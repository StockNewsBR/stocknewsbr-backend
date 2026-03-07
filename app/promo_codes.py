from datetime import datetime
from sqlalchemy.orm import Session
from app.models import PromoCode


def redeem_promo_code(db: Session, user_id: int, code: str):

    promo = db.query(PromoCode).filter(PromoCode.code == code).first()

    if not promo:
        return {"error": "Invalid promo code"}

    now = datetime.utcnow()

    if promo.starts_at and promo.starts_at > now:
        return {"error": "Promotion not started"}

    if promo.expires_at and promo.expires_at < now:
        return {"error": "Promotion expired"}

    if promo.max_uses and promo.current_uses >= promo.max_uses:
        return {"error": "Promo code fully used"}

    promo.current_uses += 1

    db.commit()

    return {
        "status": "success",
        "code": promo.code,
        "free_year": promo.free_year,
        "free_months": promo.free_months
    }