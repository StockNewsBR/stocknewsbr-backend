# ==========================================================
# STOCKNEWSBR AUTH AUDIT SERVICE (MISSION 31B)
# ==========================================================
# Persists authentication/security events without secrets:
# never stores OTP codes, digests, raw tokens, JWTs, cookies,
# Authorization headers, peppers or full unnecessary e-mails.

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.settings import get_otp_pepper
from app.models import AuthAuditEvent

logger = logging.getLogger("stocknewsbr.auth.audit")

USER_AGENT_MAX_LENGTH = 200
SID_REF_LENGTH = 16
EMAIL_HASH_LENGTH = 32
IP_HASH_LENGTH = 32

AUTH_EVENTS = frozenset(
    {
        "login_code_requested",
        "login_code_delivery_started",
        "login_code_sent",
        "login_code_delivery_failed",
        "login_code_verified",
        "login_code_invalid",
        "login_code_expired",
        "login_code_rate_limited",
        "login_success",
        "login_failed",
        "session_created",
        "session_revoked",
        "session_expired",
        "session_replaced_by_new_login",
        "logout",
        "logout_all",
        "protected_action_blocked",
        "email_change_requested",
        "email_change_verified",
        "email_changed",
        "email_change_failed",
        # Mission 31B.1: official identity / anti-impersonation trail.
        "impersonation_blocked",
        "official_identity_provisioned",
        "official_content_published",
        "bot_content_blocked",
    }
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_email(email: str | None) -> str:
    return str(email or "").strip().lower()


def mask_email(email: str | None) -> str:
    normalized = normalize_email(email)

    if not normalized or "@" not in normalized:
        return "***"

    local, _, domain = normalized.partition("@")
    domain_head, _, domain_tail = domain.partition(".")
    masked_local = (local[0] + "***") if local else "***"
    masked_domain = (domain_head[0] + "***") if domain_head else "***"

    if domain_tail:
        return f"{masked_local}@{masked_domain}.{domain_tail}"

    return f"{masked_local}@{masked_domain}"


def _keyed_digest(context: str, value: str) -> str:
    message = f"{context}:{value}".encode("utf-8")
    return hmac.new(get_otp_pepper().encode("utf-8"), message, hashlib.sha256).hexdigest()


def hash_email(email: str | None) -> str | None:
    normalized = normalize_email(email)

    if not normalized:
        return None

    return _keyed_digest("audit-email", normalized)[:EMAIL_HASH_LENGTH]


def hash_ip(ip: str | None) -> str | None:
    normalized = str(ip or "").strip()

    if not normalized:
        return None

    return _keyed_digest("audit-ip", normalized)[:IP_HASH_LENGTH]


def sid_ref(session_id: str | None) -> str | None:
    normalized = str(session_id or "").strip()

    if not normalized:
        return None

    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:SID_REF_LENGTH]


def summarize_user_agent(user_agent: str | None) -> str | None:
    normalized = str(user_agent or "").strip()

    if not normalized:
        return None

    return normalized[:USER_AGENT_MAX_LENGTH]


def record_auth_event(
    db: Session,
    event: str,
    *,
    user_id: int | None = None,
    email: str | None = None,
    ip_hash_value: str | None = None,
    user_agent: str | None = None,
    session_id: str | None = None,
    reason: str | None = None,
    status: str | None = None,
    correlation_id: str | None = None,
) -> AuthAuditEvent:
    if event not in AUTH_EVENTS:
        raise ValueError(f"unknown_auth_event:{event}")

    record = AuthAuditEvent(
        event=event,
        user_id=user_id,
        email_masked=mask_email(email) if email else None,
        email_hash=hash_email(email),
        ip_hash=ip_hash_value,
        user_agent=summarize_user_agent(user_agent),
        sid_ref=sid_ref(session_id),
        reason=(str(reason)[:200] if reason else None),
        status=(str(status)[:60] if status else None),
        correlation_id=(str(correlation_id)[:64] if correlation_id else None),
        created_at=utcnow(),
    )
    db.add(record)
    return record


def count_events_since(
    db: Session,
    event: str,
    *,
    email_hash_value: str | None = None,
    ip_hash_value: str | None = None,
    window_seconds: int,
) -> int:
    since = utcnow() - timedelta(seconds=window_seconds)
    query = (
        db.query(func.count(AuthAuditEvent.id))
        .filter(AuthAuditEvent.event == event)
        .filter(AuthAuditEvent.created_at >= since)
    )

    if email_hash_value is not None:
        query = query.filter(AuthAuditEvent.email_hash == email_hash_value)

    if ip_hash_value is not None:
        query = query.filter(AuthAuditEvent.ip_hash == ip_hash_value)

    return int(query.scalar() or 0)


def last_event_at(
    db: Session,
    event: str,
    *,
    email_hash_value: str | None = None,
    window_seconds: int,
) -> datetime | None:
    since = utcnow() - timedelta(seconds=window_seconds)
    query = (
        db.query(func.max(AuthAuditEvent.created_at))
        .filter(AuthAuditEvent.event == event)
        .filter(AuthAuditEvent.created_at >= since)
    )

    if email_hash_value is not None:
        query = query.filter(AuthAuditEvent.email_hash == email_hash_value)

    return query.scalar()
