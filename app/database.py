# =====================================================
# STOCKNEWSBR DATABASE
# =====================================================

import logging
import os
import re

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.settings import validate_database_configuration

# =====================================================
# LOGGER
# =====================================================

logger = logging.getLogger("stocknewsbr.database")


def _to_int(value, default, minimum=1):
    try:
        converted = int(value)
    except Exception:
        return default

    if converted < minimum:
        return default

    return converted


# =====================================================
# DATABASE URL
# =====================================================

DATABASE_URL = validate_database_configuration()

SQLITE_BUSY_TIMEOUT_SECONDS = _to_int(
    os.getenv("SQLITE_BUSY_TIMEOUT", "30"),
    30,
)

engine_kwargs = {
    "pool_pre_ping": True,
    "future": True,
}

if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {
        "check_same_thread": False,
        "timeout": SQLITE_BUSY_TIMEOUT_SECONDS,
    }
else:
    engine_kwargs.update(
        {
            "pool_size": _to_int(os.getenv("DB_POOL_SIZE", "10"), 10),
            "max_overflow": _to_int(os.getenv("DB_MAX_OVERFLOW", "20"), 20, minimum=0),
            "pool_timeout": _to_int(os.getenv("DB_POOL_TIMEOUT", "30"), 30),
            "pool_recycle": _to_int(os.getenv("DB_POOL_RECYCLE", "1800"), 1800),
        }
    )


# =====================================================
# ENGINE
# =====================================================

engine = create_engine(
    DATABASE_URL,
    **engine_kwargs,
)


if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()

        try:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_SECONDS * 1000};")
        finally:
            cursor.close()


# =====================================================
# SESSION
# =====================================================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=engine,
)


# =====================================================
# TRANSACTION-LOCAL POSTGRESQL RLS CONTEXT
# =====================================================

RLS_CONTEXT_INFO_KEY = "stocknewsbr_rls_context"
RLS_ALLOWED_ROLES = frozenset({"admin", "readonly", "service", "user", "worker"})
RLS_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
RLS_CONTEXT_STATEMENT = text(
    """
    SELECT
        set_config('app.current_user_id', :current_user_id, true),
        set_config('app.current_actor_id', :current_actor_id, true),
        set_config('app.current_role', :current_role, true),
        set_config('app.request_id', :request_id, true)
    """
)


def _positive_context_id(name: str, value: int) -> str:
    if isinstance(value, bool):
        raise ValueError(f"{name}_INVALID")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}_INVALID") from exc
    if normalized <= 0:
        raise ValueError(f"{name}_INVALID")
    return str(normalized)


def _normalized_rls_context(
    *,
    current_user_id: int,
    current_actor_id: int | None,
    current_role: str,
    request_id: str | None,
) -> dict[str, str]:
    user_id = _positive_context_id("RLS_CONTEXT_USER_ID", current_user_id)
    actor_id = _positive_context_id(
        "RLS_CONTEXT_ACTOR_ID",
        current_user_id if current_actor_id is None else current_actor_id,
    )
    role = str(current_role or "").strip().lower()
    if role not in RLS_ALLOWED_ROLES:
        raise ValueError("RLS_CONTEXT_ROLE_INVALID")
    normalized_request_id = str(request_id or "").strip()
    if normalized_request_id and not RLS_REQUEST_ID_PATTERN.fullmatch(normalized_request_id):
        raise ValueError("RLS_CONTEXT_REQUEST_ID_INVALID")
    return {
        "current_user_id": user_id,
        "current_actor_id": actor_id,
        "current_role": role,
        "request_id": normalized_request_id,
    }


def _is_postgresql_session(session: Session) -> bool:
    bind = session.get_bind()
    return str(getattr(getattr(bind, "dialect", None), "name", "")) == "postgresql"


def apply_rls_context(
    session: Session,
    *,
    current_user_id: int,
    current_actor_id: int | None = None,
    current_role: str = "user",
    request_id: str | None = None,
) -> None:
    if not _is_postgresql_session(session):
        return
    if not session.in_transaction():
        raise RuntimeError("RLS_CONTEXT_REQUIRES_ACTIVE_TRANSACTION")

    context = _normalized_rls_context(
        current_user_id=current_user_id,
        current_actor_id=current_actor_id,
        current_role=current_role,
        request_id=request_id,
    )
    session.info[RLS_CONTEXT_INFO_KEY] = context
    session.execute(RLS_CONTEXT_STATEMENT, context)


def clear_rls_context(session: Session) -> None:
    session.info.pop(RLS_CONTEXT_INFO_KEY, None)


def _reapply_rls_context_after_begin(session, _transaction, connection) -> None:
    if str(getattr(connection.dialect, "name", "")) != "postgresql":
        return
    context = session.info.get(RLS_CONTEXT_INFO_KEY)
    if context:
        connection.execute(RLS_CONTEXT_STATEMENT, context)


_RLS_LISTENER_MARKER = "_stocknewsbr_rls_after_begin_registered"
if not getattr(Session, _RLS_LISTENER_MARKER, False):
    event.listen(Session, "after_begin", _reapply_rls_context_after_begin)
    setattr(Session, _RLS_LISTENER_MARKER, True)


# =====================================================
# BASE
# =====================================================

Base = declarative_base()


# =====================================================
# DEPENDENCY
# =====================================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        clear_rls_context(db)
        db.close()
