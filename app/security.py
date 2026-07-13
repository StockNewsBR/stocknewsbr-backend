# ==========================================================
# STOCKNEWSBR SECURITY
# ==========================================================

import logging
import os
from datetime import datetime, timedelta

import bcrypt as raw_bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.settings import get_secret_key, session_cookie_name
from app.database import get_db
from app.models import User, UserSession

logger = logging.getLogger("stocknewsbr.security")

ALGORITHM = "HS256"
ALLOWED_JWT_ALGORITHMS = [ALGORITHM]
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))

SESSION_REPLACED_REASONS = {"session_replaced_by_new_login", "replaced_by_new_login"}
SESSION_REPLACED_DETAIL = "session_replaced"

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        if str(hashed_password or "").startswith("$2"):
            return raw_bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )

        return pwd_context.verify(plain_password, hashed_password)
    except Exception as exc:
        logger.error("Password verification error: %s", exc)
        return False


def _normalize_access_token_subject(subject):
    if subject is None or isinstance(subject, bool):
        raise ValueError("Access token subject must be integer-compatible")

    try:
        normalized = int(subject)
        if str(normalized) != str(subject):
            raise ValueError("Access token subject must be integer-compatible")
        return normalized
    except (TypeError, ValueError) as exc:
        raise ValueError("Access token subject must be integer-compatible") from exc


def get_jwt_secret() -> str:
    return get_secret_key()


def create_access_token(data: dict):
    to_encode = data.copy()
    if "sub" not in to_encode:
        raise ValueError("Access token subject is required")

    to_encode["sub"] = str(_normalize_access_token_subject(to_encode["sub"]))

    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})

    return jwt.encode(
        to_encode,
        get_jwt_secret(),
        algorithm=ALGORITHM,
    )


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_request_token(
    request: Request,
    bearer_token: str | None = Depends(oauth2_scheme),
) -> str | None:
    """Mission 31B token extraction: Authorization Bearer or session cookie."""
    if bearer_token:
        return bearer_token

    cookie_token = request.cookies.get(session_cookie_name())

    if cookie_token:
        return cookie_token

    return None


def decode_access_token_payload(token: str, credentials_exception: HTTPException | None = None):
    fallback_exception = credentials_exception or HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
    )

    try:
        # Server-side algorithm allowlist: alg=none and any non-HS256
        # algorithm are rejected by PyJWT when the list is explicit.
        payload = jwt.decode(token, get_jwt_secret(), algorithms=ALLOWED_JWT_ALGORITHMS)
        user_id = payload.get("sub")

        if user_id is None:
            raise fallback_exception

        payload["sub"] = _normalize_access_token_subject(user_id)
        return payload
    except (jwt.PyJWTError, ValueError, TypeError):
        raise fallback_exception


def resolve_token_user(
    token: str,
    db: Session,
    credentials_exception: HTTPException | None = None,
):
    fallback_exception = credentials_exception or HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
    )

    payload = decode_access_token_payload(token, fallback_exception)

    session_id = payload.get("sid")

    # Mission 31B legacy-token policy: immediate revocation. A valid signature
    # is not enough — every accepted token must carry a sid whose session is
    # alive server-side, for every plan.
    if not session_id:
        raise fallback_exception

    user = db.query(User).filter(User.id == payload["sub"]).first()

    if user is None:
        raise fallback_exception

    session = (
        db.query(UserSession)
        .filter(UserSession.user_id == user.id)
        .filter(UserSession.session_id == str(session_id))
        .first()
    )

    if session is None:
        raise fallback_exception

    if session.revoked_at is not None:
        if str(session.revoked_reason or "") in SESSION_REPLACED_REASONS:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=SESSION_REPLACED_DETAIL,
            )
        raise fallback_exception

    now = datetime.utcnow()

    if session.expires_at is not None and session.expires_at < now:
        session.revoked_at = now
        session.revoked_reason = "session_expired"
        db.add(session)
        raise fallback_exception

    session.last_seen_at = now
    db.add(session)

    return user


def get_current_user(
    token: str | None = Depends(get_request_token),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
    )

    if not token:
        raise credentials_exception

    return resolve_token_user(token, db, credentials_exception)
