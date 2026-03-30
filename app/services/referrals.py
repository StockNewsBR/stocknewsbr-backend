# =====================================================
# REFERRAL SERVICE
# Fast + Crash Safe
# =====================================================

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models import Referral, ReferralStats, User


logger = logging.getLogger("stocknewsbr.referrals")


# ============================================
# REGISTER REFERRAL
# ============================================

def register_referral(db: Session, referrer_id: int, new_user_id: int):

    if not referrer_id or not new_user_id:
        return False

    if referrer_id == new_user_id:
        return False

    try:

        existing = db.query(Referral).filter(
            Referral.referred_user_id == new_user_id
        ).first()

        if existing:
            return False

        referral = Referral(
            referrer_id=referrer_id,
            referred_user_id=new_user_id,
            status="pending",
            created_at=datetime.now(timezone.utc)
        )

        db.add(referral)

        stats = db.query(ReferralStats).filter(
            ReferralStats.user_id == referrer_id
        ).first()

        if not stats:

            stats = ReferralStats(
                user_id=referrer_id,
                total_validated=0,
                total_active=0,
                benefit_level=0,
                reward_balance_months=0
            )

            db.add(stats)

        db.commit()

        return True

    except SQLAlchemyError as e:

        db.rollback()

        logger.error(f"Referral register error: {e}")

        return False


# ============================================
# VALIDATE REFERRALS
# ============================================

def validate_referrals(db: Session):

    try:

        referrals = db.query(Referral).filter(
            Referral.status == "active"
        ).all()

        now = datetime.now(timezone.utc)

        for ref in referrals:

            if not ref.validated_at:
                continue

            if ref.reward_processed:
                continue

            if now - ref.validated_at < timedelta(days=7):
                continue

            stats = db.query(ReferralStats).filter(
                ReferralStats.user_id == ref.referrer_id
            ).first()

            if not stats:
                continue

            stats.total_validated += 1

            check_rewards(db, stats)

            ref.reward_processed = True

        db.commit()

    except SQLAlchemyError as e:

        db.rollback()

        logger.error(f"Referral validation error: {e}")


# ============================================
# REWARD SYSTEM
# ============================================

def check_rewards(db: Session, stats: ReferralStats):

    try:

        user = db.query(User).filter(
            User.id == stats.user_id
        ).first()

        if not user:
            return

        validated = stats.total_validated

        now = datetime.now(timezone.utc)

        # ----------------------------------------
        # 50 referrals = 1 month
        # ----------------------------------------

        if validated > 0 and validated % 50 == 0:

            stats.reward_balance_months += 1

            if user.plan_expires_at:

                user.plan_expires_at += timedelta(days=30)

            else:

                user.plan_expires_at = now + timedelta(days=30)

        # ----------------------------------------
        # 300 referrals = 1 year
        # ----------------------------------------

        if validated == 300:

            if user.plan_expires_at:

                user.plan_expires_at += timedelta(days=365)

            else:

                user.plan_expires_at = now + timedelta(days=365)

    except Exception as e:

        logger.error(f"Referral reward error: {e}")