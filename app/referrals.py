from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.models import Referral, ReferralStats, User


# ============================================
# REGISTER REFERRAL WHEN USER SIGNUP
# ============================================

def register_referral(db: Session, referrer_id: int, new_user_id: int):

    if referrer_id == new_user_id:
        return

    existing = db.query(Referral).filter(
        Referral.referred_user_id == new_user_id
    ).first()

    if existing:
        return

    referral = Referral(
        referrer_id=referrer_id,
        referred_user_id=new_user_id,
        status="pending"
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


# ============================================
# VALIDATE AFTER 7 DAYS
# ============================================

def validate_referrals(db: Session):

    referrals = db.query(Referral).filter(
        Referral.status == "active"
    ).all()

    for ref in referrals:

        if not ref.validated_at:
            continue

        days = datetime.utcnow() - ref.validated_at

        if days >= timedelta(days=7):

            stats = db.query(ReferralStats).filter(
                ReferralStats.user_id == ref.referrer_id
            ).first()

            stats.total_validated += 1

            check_rewards(db, stats)

    db.commit()


# ============================================
# REWARD SYSTEM
# ============================================

def check_rewards(db: Session, stats: ReferralStats):

    user = db.query(User).filter(
        User.id == stats.user_id
    ).first()

    validated = stats.total_validated

    # 50 referrals = 1 month

    if validated % 50 == 0:

        stats.reward_balance_months += 1

        if user.plan_expires_at:
            user.plan_expires_at += timedelta(days=30)

        else:
            user.plan_expires_at = datetime.utcnow() + timedelta(days=30)

    # 300 referrals = 1 year

    if validated == 300:

        if user.plan_expires_at:
            user.plan_expires_at += timedelta(days=365)

        else:
            user.plan_expires_at = datetime.utcnow() + timedelta(days=365)