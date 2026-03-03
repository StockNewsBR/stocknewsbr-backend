from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime


# ==========================================================
# USER MODEL
# ==========================================================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)

    # ==============================
    # ACCOUNT STATUS
    # ==============================

    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    # ==============================
    # PLAN STRUCTURE (SaaS)
    # ==============================

    plan = Column(String, default="trial")
    # trial, free, pro, enterprise

    plan_status = Column(String, default="active")
    # active, canceled, past_due, expired

    trial_expires_at = Column(DateTime, nullable=True)
    plan_expires_at = Column(DateTime, nullable=True)

    # ==============================
    # STRIPE FUTURE INTEGRATION
    # ==============================

    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)

    # ==============================
    # REFERRAL SYSTEM
    # ==============================

    referral_code = Column(String, unique=True, index=True)

    # ==============================
    # METADATA
    # ==============================

    created_at = Column(DateTime, default=datetime.utcnow)


# ==========================================================
# REFERRALS (INDICATION SYSTEM)
# ==========================================================

class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True, index=True)

    referrer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    referred_user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    status = Column(String, default="pending")
    # pending | active | canceled

    created_at = Column(DateTime, default=datetime.utcnow)
    validated_at = Column(DateTime, nullable=True)


# ==========================================================
# REFERRAL STATS (DYNAMIC MODEL B)
# ==========================================================

class ReferralStats(Base):
    __tablename__ = "referral_stats"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)

    total_validated = Column(Integer, default=0)
    total_active = Column(Integer, default=0)

    benefit_level = Column(Integer, default=0)
    reward_balance_months = Column(Integer, default=0)