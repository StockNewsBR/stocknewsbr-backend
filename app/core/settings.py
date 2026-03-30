# =====================================================
# STOCKNEWSBR GLOBAL SETTINGS
# =====================================================

import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger("stocknewsbr.settings")

# =====================================================
# LOAD ENV (SAFE)
# =====================================================

ENV = os.getenv("ENV", "development")

if ENV != "production":
    load_dotenv()


# =====================================================
# SAFE CONVERTERS
# =====================================================

def to_int(value, default, minimum=None):

    try:
        v = int(value)

        if minimum is not None and v < minimum:
            return default

        return v

    except Exception:
        return default


def to_bool(value, default=False):

    if value is None:
        return default

    value = str(value).lower()

    if value in ["1", "true", "yes"]:
        return True

    if value in ["0", "false", "no"]:
        return False

    return default


# =====================================================
# SETTINGS CLASS
# =====================================================

class Settings:

    # -------------------------------------------------
    # APP
    # -------------------------------------------------

    APP_NAME: str = "StockNewsBR"

    VERSION: str = "1.0"

    ENV: str = ENV

    DEBUG: bool = ENV != "production"

    # -------------------------------------------------
    # ENGINE
    # -------------------------------------------------

    SCAN_INTERVAL: int = to_int(
        os.getenv("SCAN_INTERVAL", 60),
        60,
        minimum=5
    )

    MAX_WORKERS: int = to_int(
        os.getenv("MAX_WORKERS", 12),
        12,
        minimum=1
    )

    THREAD_POOL_WORKERS: int = to_int(
        os.getenv("THREAD_POOL_WORKERS", 8),
        8,
        minimum=1
    )

    # -------------------------------------------------
    # CACHE
    # -------------------------------------------------

    MARKET_CACHE_TTL: int = to_int(
        os.getenv("MARKET_CACHE_TTL", 30),
        30,
        minimum=5
    )

    SIGNAL_CACHE_TTL: int = to_int(
        os.getenv("SIGNAL_CACHE_TTL", 60),
        60,
        minimum=5
    )

    SNAPSHOT_CACHE_TTL: int = to_int(
        os.getenv("SNAPSHOT_CACHE_TTL", 60),
        60,
        minimum=5
    )

    # -------------------------------------------------
    # MARKET DATA
    # -------------------------------------------------

    MARKET_DATA_PERIOD: str = os.getenv(
        "MARKET_DATA_PERIOD",
        "1d"
    )

    MARKET_DATA_INTERVAL: str = os.getenv(
        "MARKET_DATA_INTERVAL",
        "5m"
    )

    # -------------------------------------------------
    # API
    # -------------------------------------------------

    API_TIMEOUT: int = to_int(
        os.getenv("API_TIMEOUT", 10),
        10,
        minimum=1
    )

    API_RATE_LIMIT: str = os.getenv(
        "API_RATE_LIMIT",
        "60/minute"
    )

    # -------------------------------------------------
    # TELEGRAM
    # -------------------------------------------------

    TELEGRAM_TOKEN: str = os.getenv(
        "TELEGRAM_TOKEN",
        ""
    )

    TELEGRAM_CHAT_ID: str = os.getenv(
        "TELEGRAM_CHAT_ID",
        ""
    )

    TELEGRAM_TIMEOUT: int = to_int(
        os.getenv("TELEGRAM_TIMEOUT", 5),
        5,
        minimum=1
    )

    # -------------------------------------------------
    # DATABASE
    # -------------------------------------------------

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./stocknews.db"
    )

    # -------------------------------------------------
    # SECURITY
    # -------------------------------------------------

    SECRET_KEY: str = os.getenv(
        "SECRET_KEY",
        "change_this_in_production"
    )

    ACCESS_TOKEN_EXPIRE_MINUTES: int = to_int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60),
        60,
        minimum=5
    )

    # -------------------------------------------------
    # REDIS (FUTURE SCALE)
    # -------------------------------------------------

    REDIS_HOST: str = os.getenv(
        "REDIS_HOST",
        "localhost"
    )

    REDIS_PORT: int = to_int(
        os.getenv("REDIS_PORT", 6379),
        6379,
        minimum=1
    )

    REDIS_DB: int = to_int(
        os.getenv("REDIS_DB", 0),
        0,
        minimum=0
    )


# =====================================================
# INSTANCE
# =====================================================

settings = Settings()

logger.info(
    f"Settings loaded | ENV={settings.ENV} | DEBUG={settings.DEBUG}"
)
