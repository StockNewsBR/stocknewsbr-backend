from sqlalchemy import Column, Integer, String, DateTime, Boolean
from app.database import Base
from datetime import datetime


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
    # METADATA
    # ==============================

    created_at = Column(DateTime, default=datetime.utcnow)