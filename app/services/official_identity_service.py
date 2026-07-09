# ==========================================================
# STOCKNEWSBR — MISSION 31B.1
# Official identities (account + bot) and bot least-privilege guard
# ==========================================================
#
# Canonical, forge-proof definitions of the official StockNewsBR account and
# the official bot. Their trust flags (official / verified / role / is_bot)
# live in dedicated backend columns and are seeded here — never settable by a
# regular user through any payload.

from __future__ import annotations

import logging
import re
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import User, UserSession


logger = logging.getLogger("stocknewsbr.official_identity")


# ----------------------------------------------------------
# Roles (Mission 31B.1 §5) — least privilege, no full RBAC.
# ----------------------------------------------------------
ROLE_USER = "user"
ROLE_OFFICIAL = "official"
ROLE_BOT = "bot"
ROLE_SYSTEM = "system"
ROLE_MODERATOR = "moderator"
ROLE_ADMIN = "admin"

ALLOWED_ROLES = frozenset(
    {ROLE_USER, ROLE_OFFICIAL, ROLE_BOT, ROLE_SYSTEM, ROLE_MODERATOR, ROLE_ADMIN}
)

# Roles that legitimately carry the official badge / privileged identity.
PRIVILEGED_ROLES = frozenset({ROLE_OFFICIAL, ROLE_BOT, ROLE_SYSTEM, ROLE_ADMIN})
LOGIN_DISABLED_PASSWORD_HASH = "!"
OFFICIAL_IDENTITY_SESSION_REVOKE_REASON = "official_identity_seed_reconciled"


class OfficialIdentityConflictError(RuntimeError):
    """Raised when a reserved official identity email belongs to a non-canonical user."""


# ----------------------------------------------------------
# Canonical official identities (Mission 31B.1 §1, §2)
# ----------------------------------------------------------
OFFICIAL_ACCOUNT = {
    "email": "oficial@stocknewsbr.com",
    "display_name": "StockNewsBR Oficial",
    "official": True,
    "is_verified": True,
    "role": ROLE_OFFICIAL,
    "is_bot": False,
    "official_identity_locked": True,
}

OFFICIAL_BOT = {
    "email": "bot@stocknewsbr.com",
    "display_name": "StockNewsBR Bot",
    "username": "stocknewsbr_bot",
    "official": True,
    "is_verified": True,
    "role": ROLE_BOT,
    "is_bot": True,
    "official_identity_locked": True,
}

OFFICIAL_SERVICE_EMAILS = frozenset(
    {
        OFFICIAL_ACCOUNT["email"],
        OFFICIAL_BOT["email"],
    }
)


def is_privileged_role(role: str | None) -> bool:
    return str(role or ROLE_USER).strip().lower() in PRIVILEGED_ROLES


def normalize_email(value: str | None) -> str:
    return str(value or "").strip().lower()


def is_official_service_email(value: str | None) -> bool:
    return normalize_email(value) in OFFICIAL_SERVICE_EMAILS


def user_is_official(user: User) -> bool:
    """Trust decision for the official badge — backend flags only."""
    return bool(getattr(user, "official", False)) and is_privileged_role(
        getattr(user, "role", ROLE_USER)
    )


# ----------------------------------------------------------
# Bot least-privilege content guard (Mission 31B.1 §2)
# ----------------------------------------------------------
# The bot must never fabricate a recommendation/trade, publish news without a
# source, or fire an operational alert before Mission 32.
_TRADE_SIGNAL_PATTERN = re.compile(
    r"(?<![a-z])(buy|sell|short|cover|compra(?:r)?|venda|vender|comprar)(?![a-z])",
    re.IGNORECASE,
)
_ALERT_PATTERN = re.compile(
    r"(?<![a-z])(alerta|alert|sinal operacional|signal)(?![a-z])",
    re.IGNORECASE,
)


def assert_bot_content_allowed(text: str | None, *, has_source: bool = False) -> str | None:
    """Return a block reason if a bot post violates least privilege, else None.

    - No BUY/SELL/SHORT/COVER (Mission 31B.1 §2, test 13).
    - No news without an auditable source (test 14).
    - No operational alert before Mission 32 (test 15).
    """
    body = str(text or "")
    if _TRADE_SIGNAL_PATTERN.search(body):
        return "bot_trade_signal_forbidden"
    if _ALERT_PATTERN.search(body):
        return "bot_operational_alert_forbidden_before_mission32"
    if not has_source:
        return "bot_content_requires_source"
    return None


# ----------------------------------------------------------
# Idempotent seed (Mission 31B.1 §1, §2)
# ----------------------------------------------------------
def _is_canonical_locked_identity(user: User, spec: dict) -> bool:
    return (
        bool(getattr(user, "official", False)) == bool(spec["official"])
        and bool(getattr(user, "is_verified", False)) == bool(spec["is_verified"])
        and str(getattr(user, "role", ROLE_USER) or ROLE_USER).strip().lower()
        == spec["role"]
        and bool(getattr(user, "is_bot", False)) == bool(spec["is_bot"])
        and bool(getattr(user, "official_identity_locked", False))
        == bool(spec["official_identity_locked"])
    )


def _raise_identity_conflict(key: str, user: User, spec: dict) -> None:
    logger.error(
        "Official identity seed conflict: key=%s email=%s user_id=%s role=%s official=%s is_bot=%s locked=%s",
        key,
        spec["email"],
        getattr(user, "id", None),
        getattr(user, "role", None),
        getattr(user, "official", None),
        getattr(user, "is_bot", None),
        getattr(user, "official_identity_locked", None),
    )
    raise OfficialIdentityConflictError(f"official_identity_conflict:{key}")


def _revoke_identity_sessions(db: Session, user: User) -> int:
    if not getattr(user, "id", None):
        return 0
    result = db.execute(
        update(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
        )
        .values(
            revoked_at=datetime.utcnow(),
            revoked_reason=OFFICIAL_IDENTITY_SESSION_REVOKE_REASON,
        )
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


def _apply_identity(user: User, spec: dict) -> None:
    user.display_name = spec["display_name"]
    user.password_hash = LOGIN_DISABLED_PASSWORD_HASH
    user.official = spec["official"]
    user.is_verified = spec["is_verified"]
    user.role = spec["role"]
    user.is_bot = spec["is_bot"]
    user.official_identity_locked = spec["official_identity_locked"]
    user.is_active = True


def ensure_official_identities(db: Session) -> dict[str, User]:
    """Create or reconcile the official account and bot. Idempotent and fail-closed."""
    import secrets

    results: dict[str, User] = {}
    resolved: list[tuple[str, dict, User, bool]] = []
    for key, spec in (("official", OFFICIAL_ACCOUNT), ("bot", OFFICIAL_BOT)):
        user = db.query(User).filter(User.email == spec["email"]).first()
        if user is None:
            user = User(
                email=spec["email"],
                password_hash=LOGIN_DISABLED_PASSWORD_HASH,  # login-disabled service identity
                referral_code=secrets.token_hex(4).upper(),
            )
            db.add(user)
            created = True
        else:
            created = False
            if not _is_canonical_locked_identity(user, spec):
                _raise_identity_conflict(key, user, spec)
        resolved.append((key, spec, user, created))

    for key, spec, user, created in resolved:
        _apply_identity(user, spec)
        if not created:
            _revoke_identity_sessions(db, user)
        results[key] = user

    db.commit()
    for user in results.values():
        db.refresh(user)
    return results
