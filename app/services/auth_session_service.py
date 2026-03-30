import logging
import os
import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import LoginChallenge, TelegramLinkToken, User, UserSession
from app.security import create_access_token, hash_password, verify_password
from app.services.access_service import PAID_PLANS, has_channel_access, link_telegram_account, refresh_user_access, utcnow


logger = logging.getLogger("stocknewsbr.auth.sessions")

LOGIN_OTP_MINUTES = max(1, int(os.getenv("LOGIN_OTP_MINUTES", "10")))
LOGIN_OTP_MAX_ATTEMPTS = max(1, int(os.getenv("LOGIN_OTP_MAX_ATTEMPTS", "5")))
TELEGRAM_LINK_MINUTES = max(1, int(os.getenv("TELEGRAM_LINK_MINUTES", "15")))
PREMIUM_SESSION_POLICY = os.getenv("PREMIUM_SESSION_POLICY", "single_per_channel").strip().lower() or "single_per_channel"
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
AUTH_DEBUG_OTP = str(os.getenv("AUTH_DEBUG_OTP", "")).strip().lower() in {"1", "true", "yes", "on"}
ENVIRONMENT = os.getenv("ENV", "development").strip().lower()


def normalize_channel(channel: str | None) -> str:
    value = str(channel or "").strip().lower()

    if value in {"app", "android", "android_app", "google_app", "ios", "iphone", "apple_app", "mobile"}:
        return "app"
    if value in {"telegram", "bot"}:
        return "telegram"
    return "web"


def session_policy_for_user(user: User) -> str:
    return PREMIUM_SESSION_POLICY if str(user.plan).lower() in PAID_PLANS else "shared"


def login_requires_email_otp(user: User) -> bool:
    refresh_user_access(user)
    return str(user.plan).lower() in PAID_PLANS and bool(user.is_active)


def should_return_debug_otp() -> bool:
    return AUTH_DEBUG_OTP or ENVIRONMENT != "production"


def _generate_numeric_code(length: int = 6) -> str:
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(length))


def _active_sessions_query(db: Session, user: User, channel: str):
    return (
        db.query(UserSession)
        .filter(UserSession.user_id == user.id)
        .filter(UserSession.channel == channel)
        .filter(UserSession.revoked_at.is_(None))
    )


def create_user_session(
    db: Session,
    user: User,
    channel: str,
    device_id: str | None = None,
    device_label: str | None = None,
) -> UserSession:
    normalized_channel = normalize_channel(channel)
    now = utcnow()

    if session_policy_for_user(user) == "single_per_channel" and normalized_channel in {"web", "app"}:
        for current in _active_sessions_query(db, user, normalized_channel).all():
            current.revoked_at = now
            current.revoked_reason = "replaced_by_new_login"

    session = UserSession(
        user_id=user.id,
        session_id=secrets.token_urlsafe(24),
        channel=normalized_channel,
        device_id=(device_id or None),
        device_label=(device_label or None),
        issued_at=now,
        last_seen_at=now,
    )
    db.add(session)
    db.flush()
    return session


def issue_access_token_for_user(
    db: Session,
    user: User,
    channel: str,
    device_id: str | None = None,
    device_label: str | None = None,
):
    session = create_user_session(
        db=db,
        user=user,
        channel=channel,
        device_id=device_id,
        device_label=device_label,
    )
    token = create_access_token(
        {
            "sub": str(user.id),
            "sid": session.session_id,
            "channel": session.channel,
        }
    )
    return token, session


def revoke_session(
    db: Session,
    user_id: int,
    session_id: str | None,
    reason: str = "logout",
) -> bool:
    if not session_id:
        return False

    current = (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id)
        .filter(UserSession.session_id == session_id)
        .filter(UserSession.revoked_at.is_(None))
        .first()
    )

    if not current:
        return False

    current.revoked_at = utcnow()
    current.revoked_reason = reason
    db.add(current)
    return True


def start_login_challenge(
    db: Session,
    user: User,
    channel: str,
    device_id: str | None = None,
    device_label: str | None = None,
):
    normalized_channel = normalize_channel(channel)
    now = utcnow()

    for current in (
        db.query(LoginChallenge)
        .filter(LoginChallenge.user_id == user.id)
        .filter(LoginChallenge.channel == normalized_channel)
        .filter(LoginChallenge.consumed_at.is_(None))
        .all()
    ):
        current.consumed_at = now

    code = _generate_numeric_code()
    challenge = LoginChallenge(
        user_id=user.id,
        email=user.email,
        login_token=secrets.token_urlsafe(24),
        code_hash=hash_password(code),
        channel=normalized_channel,
        device_id=(device_id or None),
        device_label=(device_label or None),
        expires_at=now + timedelta(minutes=LOGIN_OTP_MINUTES),
        created_at=now,
    )
    db.add(challenge)
    db.flush()
    return challenge, code


def consume_login_challenge(
    db: Session,
    login_token: str,
    code: str,
):
    challenge = db.query(LoginChallenge).filter(LoginChallenge.login_token == login_token).first()
    now = utcnow()

    if not challenge:
        raise ValueError("otp_invalid")

    if challenge.consumed_at:
        raise ValueError("otp_already_used")

    if challenge.expires_at < now:
        challenge.consumed_at = now
        raise ValueError("otp_expired")

    challenge.attempt_count += 1

    if challenge.attempt_count > LOGIN_OTP_MAX_ATTEMPTS:
        challenge.consumed_at = now
        raise ValueError("otp_too_many_attempts")

    if not verify_password(code.strip(), challenge.code_hash):
        raise ValueError("otp_invalid")

    challenge.consumed_at = now
    db.add(challenge)
    user = db.query(User).filter(User.id == challenge.user_id).first()

    if not user:
        raise ValueError("user_not_found")

    return user, challenge.channel, challenge.device_id, challenge.device_label, challenge.expires_at


def create_telegram_link_token(
    db: Session,
    user: User,
    origin_channel: str = "app",
):
    refresh_user_access(user)

    if not has_channel_access(user, "telegram"):
        raise ValueError("telegram_access_required")

    now = utcnow()
    for current in (
        db.query(TelegramLinkToken)
        .filter(TelegramLinkToken.user_id == user.id)
        .filter(TelegramLinkToken.consumed_at.is_(None))
        .all()
    ):
        current.consumed_at = now

    token = TelegramLinkToken(
        user_id=user.id,
        link_code=secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:18].upper(),
        origin_channel=normalize_channel(origin_channel),
        expires_at=now + timedelta(minutes=TELEGRAM_LINK_MINUTES),
        created_at=now,
    )
    db.add(token)
    db.flush()

    deep_link = None
    if TELEGRAM_BOT_USERNAME:
        deep_link = f"https://t.me/{TELEGRAM_BOT_USERNAME}?start={token.link_code}"

    return token, deep_link


def consume_telegram_link_token(
    db: Session,
    link_code: str,
    telegram_id: str,
    telegram_username: str | None = None,
):
    token = db.query(TelegramLinkToken).filter(TelegramLinkToken.link_code == link_code.upper()).first()
    now = utcnow()

    if not token:
        raise ValueError("telegram_link_invalid")

    if token.consumed_at:
        raise ValueError("telegram_link_already_used")

    if token.expires_at < now:
        token.consumed_at = now
        raise ValueError("telegram_link_expired")

    user = db.query(User).filter(User.id == token.user_id).first()

    if not user:
        raise ValueError("user_not_found")

    refresh_user_access(user)

    if not has_channel_access(user, "telegram"):
        raise ValueError("telegram_access_required")

    link_telegram_account(
        db,
        user,
        telegram_id=str(telegram_id),
        telegram_username=telegram_username,
    )
    token.consumed_at = now
    db.add(token)
    db.add(user)
    return user, token
