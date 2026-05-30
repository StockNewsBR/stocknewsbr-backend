# ==========================================================
# STOCKNEWSBR DATABASE MODELS
# ==========================================================

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)

    display_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)

    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    plan = Column(String, default="trial", index=True)
    plan_status = Column(String, default="trialing", index=True)

    trial_expires_at = Column(DateTime, nullable=True)
    plan_expires_at = Column(DateTime, nullable=True)

    access_app = Column(Boolean, default=True)
    access_web = Column(Boolean, default=True)
    access_telegram = Column(Boolean, default=True)

    telegram_id = Column(String, unique=True, index=True, nullable=True)
    telegram_username = Column(String, nullable=True)

    subscription_provider = Column(String, index=True, nullable=True)
    subscription_origin = Column(String, index=True, nullable=True)
    subscription_product_id = Column(String, nullable=True)
    external_subscription_id = Column(String, index=True, nullable=True)
    google_play_purchase_token = Column(String, nullable=True)

    stripe_customer_id = Column(String, index=True, nullable=True)
    stripe_subscription_id = Column(String, index=True, nullable=True)

    legal_notice_version = Column(String, default="2026-03")
    accepted_terms_at = Column(DateTime, nullable=True)
    accepted_privacy_at = Column(DateTime, nullable=True)
    accepted_risk_notice_at = Column(DateTime, nullable=True)

    referral_code = Column(String, unique=True, index=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    last_access_at = Column(DateTime, nullable=True)

    referrals_sent = relationship(
        "Referral",
        foreign_keys="Referral.referrer_id",
        back_populates="referrer",
    )

    referrals_received = relationship(
        "Referral",
        foreign_keys="Referral.referred_user_id",
        back_populates="referred_user",
    )

    referral_stats = relationship(
        "ReferralStats",
        back_populates="user",
        uselist=False,
    )

    subscription_events = relationship(
        "SubscriptionAuditLog",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    auth_sessions = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    login_challenges = relationship(
        "LoginChallenge",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    telegram_link_tokens = relationship(
        "TelegramLinkToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True, index=True)

    referrer_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    referred_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
        index=True,
    )

    status = Column(String, default="pending", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    validated_at = Column(DateTime, nullable=True)
    reward_processed = Column(Boolean, default=False)

    referrer = relationship(
        "User",
        foreign_keys=[referrer_id],
        back_populates="referrals_sent",
    )

    referred_user = relationship(
        "User",
        foreign_keys=[referred_user_id],
        back_populates="referrals_received",
    )


class ReferralStats(Base):
    __tablename__ = "referral_stats"

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        primary_key=True,
    )

    total_validated = Column(Integer, default=0)
    total_active = Column(Integer, default=0)
    benefit_level = Column(Integer, default=0)
    reward_balance_months = Column(Integer, default=0)

    user = relationship(
        "User",
        back_populates="referral_stats",
    )


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    free_year = Column(Boolean, default=False)
    free_months = Column(Integer, nullable=True)
    max_uses = Column(Integer, nullable=True)
    current_uses = Column(Integer, default=0)
    starts_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"
    __table_args__ = (
        UniqueConstraint("promo_code_id", "user_id", name="uq_promo_redemption_user_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    promo_code_id = Column(Integer, ForeignKey("promo_codes.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    redeemed_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(String, nullable=False, default="local")
    folder = Column(String, nullable=False, default="posts")
    filename = Column(String, nullable=False)
    storage_key = Column(String, nullable=True)
    content_type = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    public_url = Column(String, nullable=True)
    status = Column(String, nullable=False, default="uploaded")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String, unique=True, index=True, nullable=False)
    channel = Column(String, nullable=False, index=True, default="web")
    device_id = Column(String, nullable=True, index=True)
    device_label = Column(String, nullable=True)
    issued_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True, index=True)
    revoked_reason = Column(String, nullable=True)

    user = relationship(
        "User",
        back_populates="auth_sessions",
    )


class LoginChallenge(Base):
    __tablename__ = "login_challenges"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    email = Column(String, nullable=False, index=True)
    login_token = Column(String, unique=True, index=True, nullable=False)
    code_hash = Column(String, nullable=False)
    channel = Column(String, nullable=False, default="web", index=True)
    device_id = Column(String, nullable=True, index=True)
    device_label = Column(String, nullable=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    consumed_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship(
        "User",
        back_populates="login_challenges",
    )


class TelegramLinkToken(Base):
    __tablename__ = "telegram_link_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    link_code = Column(String, unique=True, index=True, nullable=False)
    origin_channel = Column(String, nullable=False, default="app")
    expires_at = Column(DateTime, nullable=False, index=True)
    consumed_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship(
        "User",
        back_populates="telegram_link_tokens",
    )


class SubscriptionAuditLog(Base):
    __tablename__ = "subscription_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    provider = Column(String, index=True, nullable=False)
    event_type = Column(String, index=True, nullable=False)
    product_id = Column(String, nullable=True)
    origin = Column(String, nullable=True)
    external_subscription_id = Column(String, nullable=True)
    status = Column(String, nullable=True)
    payload_excerpt = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship(
        "User",
        back_populates="subscription_events",
    )


class SocialPost(Base):
    __tablename__ = "social_posts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    ticker = Column(String, nullable=True, index=True)
    text = Column(Text, nullable=False)
    image_url = Column(String, nullable=True)
    sentiment = Column(String, nullable=True, index=True)
    display_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class SocialComment(Base):
    __tablename__ = "social_comments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("social_posts.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    image_url = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class SocialLike(Base):
    __tablename__ = "social_likes"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_social_like_post_user"),
    )

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("social_posts.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class SocialRepost(Base):
    __tablename__ = "social_reposts"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_social_repost_post_user"),
    )

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("social_posts.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    quote_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class SocialFollow(Base):
    __tablename__ = "social_follows"
    __table_args__ = (
        UniqueConstraint("user_id", "target_user_id", name="uq_social_follow_user_target"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class SocialSentimentVote(Base):
    __tablename__ = "social_sentiment_votes"
    __table_args__ = (
        UniqueConstraint("ticker", "user_id", name="uq_social_sentiment_vote_ticker_user"),
    )

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    sentiment = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
