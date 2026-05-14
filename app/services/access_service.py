import hashlib
import logging
import os
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import SubscriptionAuditLog, User

logger = logging.getLogger("stocknewsbr.access")

SAAS_LAUNCH_DATE = date.fromisoformat(os.getenv("SAAS_LAUNCH_DATE", "2026-05-14"))
TRIAL_SHORTEN_AFTER_DAYS = max(1, int(os.getenv("TRIAL_SHORTEN_AFTER_DAYS", "30")))
INITIAL_TRIAL_DAYS = max(1, int(os.getenv("INITIAL_TRIAL_DAYS", "30")))
POST_LAUNCH_TRIAL_DAYS = max(1, int(os.getenv("POST_LAUNCH_TRIAL_DAYS", "14")))
DEFAULT_TRIAL_DAYS = INITIAL_TRIAL_DAYS
REFUND_WINDOW_DAYS = max(1, int(os.getenv("REFUND_WINDOW_DAYS", "7")))
MONTHLY_PLAN_DAYS = 31
ANNUAL_PLAN_DAYS = 365
LEGAL_NOTICE_VERSION = os.getenv("LEGAL_NOTICE_VERSION", "2026-03")
PAID_PLANS = {"premium", "enterprise"}
FREE_PLAN = "free"
TRIAL_PLAN = "trial"

PRICING_CATALOG = {
    "BR": {
        "currency": "BRL",
        "monthly_amount": 49,
        "annual_amount": 500,
        "monthly_product_id": "premium_br_monthly",
        "annual_product_id": "premium_br_annual",
        "payment_note": "Assinatura Brasil: R$49/mes ou R$500 a vista por 12 meses.",
    },
    "USA": {
        "currency": "USD",
        "monthly_amount": 49,
        "annual_amount": 500,
        "monthly_product_id": "premium_usa_monthly",
        "annual_product_id": "premium_usa_annual",
        "payment_note": "International account: USA subscription. Premium is $49/month or $500 upfront for 12 months.",
    },
}


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def trial_days_for_market(market: str | None = None, now: datetime | None = None) -> int:
    reference = (_as_naive_utc(now) or utcnow()).date()
    shorten_date = SAAS_LAUNCH_DATE + timedelta(days=TRIAL_SHORTEN_AFTER_DAYS)
    return POST_LAUNCH_TRIAL_DAYS if reference >= shorten_date else INITIAL_TRIAL_DAYS


def normalize_billing_market(value: str | None = None) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"BR", "BRA", "BRAZIL", "BRASIL", "PT-BR", "B3"}:
        return "BR"
    return "USA"


def pricing_catalog(market: str | None = None, now: datetime | None = None):
    requested_market = normalize_billing_market(market)
    catalog = {
        key: {
            **value,
            "trial_days": trial_days_for_market(key, now),
            "refund_window_days": REFUND_WINDOW_DAYS,
            "refund_policy": (
                "Cancelamento permitido em ate 7 dias. Depois disso nao ha reembolso."
                if key == "BR"
                else "Cancellation/refund window is 7 days. After that there is no refund."
            ),
        }
        for key, value in PRICING_CATALOG.items()
    }
    return {
        "market": requested_market,
        "trial_shortens_after_days": TRIAL_SHORTEN_AFTER_DAYS,
        "post_launch_trial_days": POST_LAUNCH_TRIAL_DAYS,
        "refund_window_days": REFUND_WINDOW_DAYS,
        "plans": catalog,
        "selected": catalog[requested_market],
    }


def _default_plan_days(product_id: str | None) -> int:
    product_id = str(product_id or "").lower()

    if any(token in product_id for token in {"annual", "anual", "year", "12m", "12_meses"}):
        return ANNUAL_PLAN_DAYS

    return MONTHLY_PLAN_DAYS


def generate_referral_code(seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest().upper()
    return f"SNB{digest[:8]}"


def ensure_referral_code(db: Session, user: User):
    if user.referral_code:
        return user.referral_code

    base_seed = user.email or f"user-{user.id or utcnow().timestamp()}"

    for attempt in range(20):
        suffix = "" if attempt == 0 else f"-{attempt}"
        candidate = generate_referral_code(f"{base_seed}{suffix}")
        exists = db.query(User).filter(User.referral_code == candidate).first()

        if exists and exists.id != user.id:
            continue

        user.referral_code = candidate
        return candidate

    fallback = generate_referral_code(f"{base_seed}-{utcnow().timestamp()}")
    user.referral_code = fallback
    return fallback


def accept_legal_documents(
    user: User,
    accepted_terms: bool = True,
    accepted_privacy: bool = True,
    accepted_risk_notice: bool = True,
):
    now = utcnow()
    user.legal_notice_version = LEGAL_NOTICE_VERSION

    if accepted_terms:
        user.accepted_terms_at = user.accepted_terms_at or now

    if accepted_privacy:
        user.accepted_privacy_at = user.accepted_privacy_at or now

    if accepted_risk_notice:
        user.accepted_risk_notice_at = user.accepted_risk_notice_at or now

    user.updated_at = now
    return user


def grant_trial_access(user: User, days: int | None = None, market: str | None = None, now: datetime | None = None):
    now = _as_naive_utc(now) or utcnow()
    trial_days = days if days is not None else trial_days_for_market(market, now)
    user.plan = TRIAL_PLAN
    user.plan_status = "trialing"
    user.trial_expires_at = user.trial_expires_at or (now + timedelta(days=trial_days))
    user.access_app = True
    user.access_web = True
    user.access_telegram = True
    user.updated_at = now
    return user


def downgrade_to_free(user: User, reason: str = "free_active"):
    now = utcnow()

    user.plan = FREE_PLAN
    user.plan_status = reason
    user.plan_expires_at = None
    user.access_app = True
    user.access_web = False
    user.access_telegram = False
    user.updated_at = now
    return user


def activate_subscription(
    user: User,
    provider: str,
    product_id: str,
    origin: str = "android_app",
    external_subscription_id: str | None = None,
    purchase_token: str | None = None,
    renewal_at: datetime | None = None,
    started_at: datetime | None = None,
):
    now = utcnow()

    user.plan = "premium"
    user.plan_status = "active"
    user.subscription_provider = provider
    user.subscription_origin = origin
    user.subscription_product_id = product_id
    user.external_subscription_id = external_subscription_id
    user.google_play_purchase_token = purchase_token
    user.access_app = True
    user.access_web = True
    user.access_telegram = True

    if started_at:
        user.created_at = user.created_at or _as_naive_utc(started_at)

    if renewal_at:
        user.plan_expires_at = _as_naive_utc(renewal_at)
    elif user.plan_expires_at is None or user.plan_expires_at < now:
        user.plan_expires_at = now + timedelta(days=_default_plan_days(product_id))

    user.trial_expires_at = None
    user.updated_at = now
    return user


def expire_access(user: User, reason: str = "expired"):
    now = utcnow()

    user.plan = "expired"
    user.plan_status = reason
    user.access_app = False
    user.access_web = False
    user.access_telegram = False
    user.updated_at = now
    return user


def refresh_user_access(user: User):
    now = utcnow()
    user.last_access_at = now

    if not user.is_active:
        return expire_access(user, reason="inactive")

    if user.plan == TRIAL_PLAN and user.trial_expires_at and now > user.trial_expires_at:
        return downgrade_to_free(user, reason="trial_ended")

    if user.plan in PAID_PLANS and user.plan_expires_at and now > user.plan_expires_at:
        return downgrade_to_free(user, reason="premium_expired")

    if user.plan in PAID_PLANS:
        user.plan_status = "active"
        user.access_app = True
        user.access_web = True
        user.access_telegram = True
        user.updated_at = now
        return user

    if user.plan == TRIAL_PLAN:
        user.plan_status = "trialing"
        user.access_app = True
        user.access_web = True
        user.access_telegram = True
        user.updated_at = now
        return user

    if user.plan == FREE_PLAN:
        user.plan_status = "active"
        user.access_app = True
        user.access_web = False
        user.access_telegram = False
        user.updated_at = now
        return user

    return user


def has_channel_access(user: User, channel: str | None = None) -> bool:
    refresh_user_access(user)

    if channel == "app":
        return bool(user.access_app)
    if channel == "web":
        return bool(user.access_web)
    if channel == "telegram":
        return bool(user.access_telegram)

    return any([user.access_app, user.access_web, user.access_telegram])


def link_telegram_account(
    db: Session,
    user: User,
    telegram_id: str,
    telegram_username: str | None = None,
):
    existing = db.query(User).filter(User.telegram_id == telegram_id).first()

    if existing and existing.id != user.id:
        raise ValueError("telegram_id_already_linked")

    user.telegram_id = telegram_id
    user.telegram_username = telegram_username
    user.updated_at = utcnow()
    return user


def log_subscription_event(
    db: Session,
    user: User | None,
    provider: str,
    event_type: str,
    product_id: str | None = None,
    origin: str | None = None,
    external_subscription_id: str | None = None,
    status: str | None = None,
    payload_excerpt: str | None = None,
):
    event = SubscriptionAuditLog(
        user_id=user.id if user else None,
        provider=provider,
        event_type=event_type,
        product_id=product_id,
        origin=origin,
        external_subscription_id=external_subscription_id,
        status=status,
        payload_excerpt=payload_excerpt[:4000] if payload_excerpt else None,
    )
    db.add(event)
    return event


def serialize_user_access(user: User):
    refresh_user_access(user)

    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "phone": user.phone,
        "avatar_url": user.avatar_url,
        "plan": user.plan,
        "plan_status": user.plan_status,
        "subscription_provider": user.subscription_provider,
        "subscription_origin": user.subscription_origin,
        "subscription_product_id": user.subscription_product_id,
        "trial_expires_at": user.trial_expires_at,
        "plan_expires_at": user.plan_expires_at,
        "telegram_linked": bool(user.telegram_id),
        "telegram_username": user.telegram_username,
        "referral_code": user.referral_code,
        "legal_notice_version": user.legal_notice_version,
        "accepted_terms_at": user.accepted_terms_at,
        "accepted_privacy_at": user.accepted_privacy_at,
        "accepted_risk_notice_at": user.accepted_risk_notice_at,
        "session_policy": "single_per_channel" if str(user.plan).lower() in PAID_PLANS else "shared",
        "otp_required_on_login": str(user.plan).lower() in PAID_PLANS,
        "access": {
            "app": bool(user.access_app),
            "web": bool(user.access_web),
            "telegram": bool(user.access_telegram),
        },
    }
