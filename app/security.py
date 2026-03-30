# ==========================================================
# STOCKNEWSBR SECURITY
# ==========================================================

import logging
import os
from datetime import datetime, timedelta

import bcrypt as raw_bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserSession

logger = logging.getLogger("stocknewsbr.security")

SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))
STRICT_SESSION_PLANS = {
    item.strip().lower()
    for item in os.getenv("STRICT_SESSION_PLANS", "premium,enterprise").split(",")
    if item.strip()
}

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


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})

    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def decode_access_token_payload(token: str, credentials_exception: HTTPException | None = None):
    fallback_exception = credentials_exception or HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")

        if user_id is None:
            raise fallback_exception

        payload["sub"] = int(user_id)
        return payload
    except (JWTError, ValueError, TypeError):
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
    user = db.query(User).filter(User.id == payload["sub"]).first()

    if user is None:
        raise fallback_exception

    session_id = payload.get("sid")

    if session_id:
        session = (
            db.query(UserSession)
            .filter(UserSession.user_id == user.id)
            .filter(UserSession.session_id == str(session_id))
            .filter(UserSession.revoked_at.is_(None))
            .first()
        )

        if session is None:
            raise fallback_exception

        session.last_seen_at = datetime.utcnow()
        db.add(session)
    elif str(user.plan).lower() in STRICT_SESSION_PLANS:
        raise fallback_exception

    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
    )

    return resolve_token_user(token, db, credentials_exception)
