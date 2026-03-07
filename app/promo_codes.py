from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.models import PromoCode, User


def apply_promo_code(db: Session, user_id: int, code: str):

    user = db.query(User).filter(User.id == user_id).first()

    if user.plan not in ["trial", "free"]:
        return {"error": "Código só pode ser usado por usuários Free ou Trial"}

    promo = db.query(PromoCode).filter(
        PromoCode.code == code
    ).first()

    if not promo:
        return {"error": "Código inválido"}

    now = datetime.utcnow()

    if promo.starts_at and promo.starts_at > now:
        return {"error": "Promoção ainda não começou"}

    if promo.expires_at and promo.expires_at < now:
        return {"error": "Código expirado"}

    if promo.current_uses >= promo.max_uses:
        return {"error": "Código já atingiu limite"}

    promo.current_uses += 1

    if promo.free_year:

        user.plan = "pro"
        user.plan_expires_at = now + timedelta(days=365)

    elif promo.free_months:

        user.plan = "pro"
        user.plan_expires_at = now + timedelta(days=30 * promo.free_months)

    db.commit()

    return {"success": True}