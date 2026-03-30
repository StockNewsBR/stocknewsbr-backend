# =====================================================
# PROMO CODE SERVICE
# Fast + Crash Safe
# =====================================================

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models import PromoCode, PromoRedemption


logger = logging.getLogger("stocknewsbr.promo_codes")


# =====================================================
# REDEEM PROMO CODE
# =====================================================

def redeem_promo_code(db: Session, user_id: int, code: str):
    if not user_id or not code:
        return {"error": "Invalid promo code"}

    try:

        code = code.strip().upper()

        promo = (

            db.query(PromoCode)

            .filter(PromoCode.code == code)

            .with_for_update()

            .first()

        )

        if not promo:

            return {"error": "Invalid promo code"}

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # ------------------------------------------------
        # START DATE CHECK
        # ------------------------------------------------

        if promo.starts_at and promo.starts_at > now:

            return {"error": "Promotion not started"}

        # ------------------------------------------------
        # EXPIRATION CHECK
        # ------------------------------------------------

        if promo.expires_at and promo.expires_at < now:

            return {"error": "Promotion expired"}

        # ------------------------------------------------
        # USAGE LIMIT
        # ------------------------------------------------

        if promo.max_uses and promo.current_uses >= promo.max_uses:

            return {"error": "Promo code fully used"}

        existing_redemption = (
            db.query(PromoRedemption)
            .filter(PromoRedemption.promo_code_id == promo.id)
            .filter(PromoRedemption.user_id == user_id)
            .first()
        )

        if existing_redemption:
            return {"error": "Promo code already redeemed"}

        # ------------------------------------------------
        # APPLY PROMO
        # ------------------------------------------------

        promo.current_uses += 1
        db.add(
            PromoRedemption(
                promo_code_id=promo.id,
                user_id=user_id,
            )
        )

        db.commit()

        return {

            "status": "success",

            "code": promo.code,

            "free_year": promo.free_year,

            "free_months": getattr(promo, "free_months", None)

        }

    except SQLAlchemyError as e:

        db.rollback()

        logger.error(f"Promo code database error: {e}")

        return {"error": "Database error"}

    except Exception as e:

        db.rollback()

        logger.error(f"Promo code error: {e}")

        return {"error": "Promo code error"}
