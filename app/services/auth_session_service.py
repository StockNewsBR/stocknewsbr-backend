import hashlib
import hmac
import logging
import os
import secrets
from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.settings import (
    get_otp_pepper,
    login_code_expiry_seconds,
    login_code_max_attempts,
    login_code_max_sends_per_email,
    login_code_max_sends_per_ip,
    login_code_resend_cooldown_seconds,
    login_code_send_window_seconds,
)
from app.models import LoginChallenge, TelegramLinkToken, User, UserSession
from app.security import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token
from app.services import auth_audit_service as auth_audit
from app.services.access_service import PAID_PLANS, has_channel_access, link_telegram_account, refresh_user_access, utcnow


logger = logging.getLogger("stocknewsbr.auth.sessions")

TELEGRAM_LINK_MINUTES = max(1, int(os.getenv("TELEGRAM_LINK_MINUTES", "15")))
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")

CHALLENGE_PURPOSE_LOGIN = "LOGIN"
CHALLENGE_PURPOSE_EMAIL_CHANGE = "EMAIL_CHANGE"
CHALLENGE_PURPOSES = frozenset({CHALLENGE_PURPOSE_LOGIN, CHALLENGE_PURPOSE_EMAIL_CHANGE})

DELIVERY_PENDING = "PENDING"
DELIVERY_SENT = "SENT"
DELIVERY_FAILED = "FAILED"
DELIVERY_INVALIDATED = "INVALIDATED"

SESSION_REPLACED_REASON = "session_replaced_by_new_login"
SESSION_POLICY = "single"


def normalize_channel(channel: str | None) -> str:
    value = str(channel or "").strip().lower()

    if value in {"app", "android", "android_app", "google_app", "ios", "iphone", "apple_app", "mobile"}:
        return "app"
    if value in {"telegram", "bot"}:
        return "telegram"
    return "web"


def normalize_email(email: str | None) -> str:
    return str(email or "").strip().lower()


def session_policy_for_user(user: User) -> str:
    del user
    return SESSION_POLICY


def login_requires_email_otp(user: User) -> bool:
    refresh_user_access(user)
    return str(user.plan).lower() in PAID_PLANS and bool(user.is_active)


# ==========================================================
# MISSION 31B - LOGIN CODE (OTP)
# ==========================================================

def generate_login_code() -> str:
    """CSPRNG six-digit code, accepts 000000..999999 with leading zeros."""
    return f"{secrets.randbelow(1_000_000):06d}"


def build_login_code_digest(
    *,
    challenge_id: str,
    purpose: str,
    code: str,
    pepper: str | None = None,
) -> str:
    resolved_pepper = pepper if pepper is not None else get_otp_pepper()

    if not resolved_pepper:
        raise RuntimeError("OTP_PEPPER_NOT_CONFIGURED")

    message = f"{purpose}:{challenge_id}:{code}".encode("utf-8")

    return hmac.new(
        resolved_pepper.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()


def invalidate_open_challenges(
    db: Session,
    user_id: int,
    purpose: str,
    reason_status: str = DELIVERY_INVALIDATED,
) -> int:
    now = utcnow()
    result = db.execute(
        update(LoginChallenge)
        .where(
            LoginChallenge.user_id == user_id,
            LoginChallenge.purpose == purpose,
            LoginChallenge.consumed_at.is_(None),
            LoginChallenge.invalidated_at.is_(None),
        )
        .values(invalidated_at=now, delivery_status=reason_status)
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


def start_login_challenge(
    db: Session,
    user: User,
    channel: str,
    device_id: str | None = None,
    device_label: str | None = None,
    *,
    purpose: str = CHALLENGE_PURPOSE_LOGIN,
    target_email: str | None = None,
    request_ip_hash: str | None = None,
    correlation_id: str | None = None,
):
    if purpose not in CHALLENGE_PURPOSES:
        raise ValueError("challenge_purpose_invalid")

    normalized_channel = normalize_channel(channel)
    now = utcnow()

    invalidate_open_challenges(db, user.id, purpose)

    code = generate_login_code()
    login_token = secrets.token_urlsafe(24)
    challenge = LoginChallenge(
        user_id=user.id,
        email=normalize_email(user.email),
        login_token=login_token,
        code_hash=build_login_code_digest(
            challenge_id=login_token,
            purpose=purpose,
            code=code,
        ),
        purpose=purpose,
        target_email=normalize_email(target_email) or None,
        channel=normalized_channel,
        device_id=(device_id or None),
        device_label=(device_label or None),
        max_attempts=login_code_max_attempts(),
        delivery_status=DELIVERY_PENDING,
        expires_at=now + timedelta(seconds=login_code_expiry_seconds()),
        created_at=now,
        request_ip_hash=request_ip_hash,
        correlation_id=correlation_id,
    )
    db.add(challenge)
    db.flush()
    return challenge, code


def login_code_rate_limit_state(
    db: Session,
    *,
    email: str,
    request_ip_hash: str | None,
) -> str | None:
    """Returns the violated limit name or None when the request is allowed."""
    email_hash_value = auth_audit.hash_email(email)
    window = login_code_send_window_seconds()

    if request_ip_hash and auth_audit.count_events_since(
        db,
        "login_code_requested",
        ip_hash_value=request_ip_hash,
        window_seconds=window,
    ) >= login_code_max_sends_per_ip():
        return "ip_window"

    if auth_audit.count_events_since(
        db,
        "login_code_requested",
        email_hash_value=email_hash_value,
        window_seconds=window,
    ) >= login_code_max_sends_per_email():
        return "email_window"

    cooldown_seconds = login_code_resend_cooldown_seconds()

    if cooldown_seconds > 0 and auth_audit.last_event_at(
        db,
        "login_code_requested",
        email_hash_value=email_hash_value,
        window_seconds=cooldown_seconds,
    ) is not None:
        return "resend_cooldown"

    return None


def request_login_code(
    db: Session,
    email: str,
    *,
    channel: str = "web",
    device_id: str | None = None,
    device_label: str | None = None,
    request_ip_hash: str | None = None,
    user_agent: str | None = None,
    correlation_id: str | None = None,
) -> dict:
    """Shared REQUEST_CODE flow. Always safe to expose a generic response.

    Commits its own outcome so rate-limit ledger entries survive any caller
    error. Returns a dict with internal status plus challenge/code when one
    was created (delivery stays PENDING; caller sends the e-mail outside the
    transaction and then marks delivery).
    """
    normalized_email = normalize_email(email)

    violated = login_code_rate_limit_state(
        db,
        email=normalized_email,
        request_ip_hash=request_ip_hash,
    )

    if violated:
        auth_audit.record_auth_event(
            db,
            "login_code_rate_limited",
            email=normalized_email,
            ip_hash_value=request_ip_hash,
            user_agent=user_agent,
            reason=violated,
            correlation_id=correlation_id,
        )
        db.commit()
        return {"status": "rate_limited", "reason": violated}

    user = db.query(User).filter(User.email == normalized_email).first()

    if user is None:
        auth_audit.record_auth_event(
            db,
            "login_code_requested",
            email=normalized_email,
            ip_hash_value=request_ip_hash,
            user_agent=user_agent,
            status="unknown_email",
            correlation_id=correlation_id,
        )
        db.commit()
        return {"status": "unknown_email"}

    refresh_user_access(user)
    db.add(user)

    if not user.is_active:
        auth_audit.record_auth_event(
            db,
            "login_code_requested",
            user_id=user.id,
            email=normalized_email,
            ip_hash_value=request_ip_hash,
            user_agent=user_agent,
            status="inactive",
            correlation_id=correlation_id,
        )
        db.commit()
        return {"status": "inactive"}

    challenge, code = start_login_challenge(
        db,
        user,
        channel=channel,
        device_id=device_id,
        device_label=device_label,
        purpose=CHALLENGE_PURPOSE_LOGIN,
        request_ip_hash=request_ip_hash,
        correlation_id=correlation_id,
    )
    auth_audit.record_auth_event(
        db,
        "login_code_requested",
        user_id=user.id,
        email=normalized_email,
        ip_hash_value=request_ip_hash,
        user_agent=user_agent,
        status="accepted",
        correlation_id=correlation_id,
    )
    db.commit()
    return {"status": "accepted", "challenge": challenge, "code": code, "user": user}


def mark_challenge_delivery(
    db: Session,
    challenge_id: int,
    status: str,
    *,
    correlation_id: str | None = None,
    email: str | None = None,
) -> None:
    if status not in {DELIVERY_SENT, DELIVERY_FAILED}:
        raise ValueError("delivery_status_invalid")

    now = utcnow()
    db.execute(
        update(LoginChallenge)
        .where(
            LoginChallenge.id == challenge_id,
            LoginChallenge.consumed_at.is_(None),
            LoginChallenge.invalidated_at.is_(None),
        )
        .values(delivery_status=status, delivery_attempted_at=now)
        .execution_options(synchronize_session=False)
    )
    auth_audit.record_auth_event(
        db,
        "login_code_sent" if status == DELIVERY_SENT else "login_code_delivery_failed",
        email=email,
        correlation_id=correlation_id,
    )
    db.commit()


def challenge_expiry_minutes(challenge: LoginChallenge) -> int:
    return max(1, int((challenge.expires_at - challenge.created_at).total_seconds() // 60))


def _consume_challenge_core(
    db: Session,
    login_token: str,
    code: str,
    *,
    purpose: str,
    expected_user_id: int | None = None,
) -> LoginChallenge:
    """Atomic VERIFY_CODE core.

    Persists the attempt counter in its own commit (survives caller errors),
    then claims the challenge with an UPDATE ... WHERE consumed_at IS NULL so
    exactly one concurrent verification wins. The winning claim is NOT
    committed here: the caller creates the session/applies the change inside
    the same transaction and commits.
    """
    now = utcnow()
    challenge = (
        db.query(LoginChallenge)
        .populate_existing()
        .filter(LoginChallenge.login_token == str(login_token or ""))
        .first()
    )

    if not challenge or challenge.purpose != purpose:
        raise ValueError("otp_invalid")

    if expected_user_id is not None and challenge.user_id != expected_user_id:
        raise ValueError("otp_invalid")

    if challenge.invalidated_at is not None:
        raise ValueError("otp_invalid")

    if challenge.consumed_at is not None:
        raise ValueError("otp_already_used")

    if challenge.expires_at < now:
        db.execute(
            update(LoginChallenge)
            .where(
                LoginChallenge.id == challenge.id,
                LoginChallenge.consumed_at.is_(None),
                LoginChallenge.invalidated_at.is_(None),
            )
            .values(invalidated_at=now, delivery_status=DELIVERY_INVALIDATED)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        raise ValueError("otp_expired")

    if challenge.delivery_status != DELIVERY_SENT:
        raise ValueError("otp_invalid")

    claimed = db.execute(
        update(LoginChallenge)
        .where(
            LoginChallenge.id == challenge.id,
            LoginChallenge.consumed_at.is_(None),
            LoginChallenge.invalidated_at.is_(None),
        )
        .values(attempt_count=LoginChallenge.attempt_count + 1)
        .execution_options(synchronize_session=False)
    )
    db.commit()

    if int(claimed.rowcount or 0) == 0:
        raise ValueError("otp_already_used")

    db.refresh(challenge)

    if challenge.attempt_count > int(challenge.max_attempts or login_code_max_attempts()):
        raise ValueError("otp_too_many_attempts")

    candidate = build_login_code_digest(
        challenge_id=challenge.login_token,
        purpose=challenge.purpose,
        code=str(code or "").strip(),
    )

    if not hmac.compare_digest(candidate, str(challenge.code_hash or "")):
        raise ValueError("otp_invalid")

    won = db.execute(
        update(LoginChallenge)
        .where(
            LoginChallenge.id == challenge.id,
            LoginChallenge.consumed_at.is_(None),
        )
        .values(consumed_at=utcnow())
        .execution_options(synchronize_session=False)
    )

    if int(won.rowcount or 0) != 1:
        raise ValueError("otp_already_used")

    db.refresh(challenge)
    return challenge


def consume_login_challenge(
    db: Session,
    login_token: str,
    code: str,
):
    challenge = _consume_challenge_core(
        db,
        login_token,
        code,
        purpose=CHALLENGE_PURPOSE_LOGIN,
    )

    user = db.query(User).filter(User.id == challenge.user_id).first()

    if not user:
        raise ValueError("user_not_found")

    return user, challenge.channel, challenge.device_id, challenge.device_label, challenge.expires_at


def consume_email_change_challenge(
    db: Session,
    login_token: str,
    code: str,
    *,
    expected_user_id: int,
) -> LoginChallenge:
    return _consume_challenge_core(
        db,
        login_token,
        code,
        purpose=CHALLENGE_PURPOSE_EMAIL_CHANGE,
        expected_user_id=expected_user_id,
    )


# ==========================================================
# MISSION 31B - SINGLE SESSION PER USER
# ==========================================================

def _active_sessions_query(db: Session, user_id: int):
    return (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id)
        .filter(UserSession.revoked_at.is_(None))
    )


def create_user_session(
    db: Session,
    user: User,
    channel: str,
    device_id: str | None = None,
    device_label: str | None = None,
    *,
    created_ip_hash: str | None = None,
    user_agent: str | None = None,
    correlation_id: str | None = None,
) -> UserSession:
    normalized_channel = normalize_channel(channel)
    now = utcnow()

    # Owner policy: one active session per (user, channel). A new login on a
    # channel kicks the previous session of THAT channel only, leaving the
    # other channels (web/app/telegram) untouched. Serialize the
    # replace-and-create block per user with a transactional row lock so two
    # concurrent logins on the same channel cannot interleave revoke+insert on
    # PostgreSQL and leave two active sessions. SQLite ignores FOR UPDATE (its
    # single-writer model already serializes the transactions).
    db.query(User.id).filter(User.id == user.id).with_for_update().first()

    # A new login revokes the previous active session on the SAME channel in
    # the same transaction that creates the replacement session.
    db.execute(
        update(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.channel == normalized_channel,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=now, revoked_reason=SESSION_REPLACED_REASON)
        .execution_options(synchronize_session=False)
    )

    session = UserSession(
        user_id=user.id,
        session_id=secrets.token_urlsafe(32),
        channel=normalized_channel,
        device_id=(device_id or None),
        device_label=(device_label or None),
        issued_at=now,
        expires_at=now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        last_seen_at=now,
        created_ip_hash=created_ip_hash,
        user_agent=auth_audit.summarize_user_agent(user_agent),
        correlation_id=correlation_id,
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
    *,
    created_ip_hash: str | None = None,
    user_agent: str | None = None,
    correlation_id: str | None = None,
):
    session = create_user_session(
        db=db,
        user=user,
        channel=channel,
        device_id=device_id,
        device_label=device_label,
        created_ip_hash=created_ip_hash,
        user_agent=user_agent,
        correlation_id=correlation_id,
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

    result = db.execute(
        update(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.session_id == str(session_id),
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow(), revoked_reason=reason)
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0) > 0


def revoke_all_sessions(
    db: Session,
    user_id: int,
    reason: str = "logout_all",
    *,
    except_session_id: str | None = None,
) -> int:
    query = update(UserSession).where(
        UserSession.user_id == user_id,
        UserSession.revoked_at.is_(None),
    )

    if except_session_id:
        query = query.where(UserSession.session_id != str(except_session_id))

    result = db.execute(
        query.values(revoked_at=utcnow(), revoked_reason=reason).execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


# ==========================================================
# TELEGRAM LINK TOKENS (unchanged contract)
# ==========================================================

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
