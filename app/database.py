# =====================================================
# STOCKNEWSBR DATABASE
# =====================================================

import logging
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

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

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./stocknews.db",
)

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
        db.close()
