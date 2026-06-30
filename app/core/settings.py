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

_PROCESS_ENV = str(os.getenv("ENV") or "").strip().lower()

if _PROCESS_ENV != "production":
    load_dotenv()


ENV = str(os.getenv("ENV", "development")).strip() or "development"
ENV_NORMALIZED = ENV.lower()
MIN_SECRET_KEY_LENGTH = 32

INSECURE_SECRET_KEY_VALUES = frozenset(
    {
        "change_this_secret",
        "change_this_in_production",
        "<defina-uma-chave-forte-fora-do-repositorio>",
        "<defina_uma_chave_forte_fora_do_repositorio>",
    }
)
TRIVIAL_SECRET_KEY_VALUES = frozenset(
    {
        "secret",
        "password",
        "changeme",
        "change_me",
        "default",
        "default_secret",
        "jwt_secret",
        "test_secret",
        "dev_secret",
        "stocknewsbr",
        "stocknewsbr_secret",
    }
)
REPEATED_TRIVIAL_SECRET_TOKENS = ("secret", "password", "changeme", "default")


def _normalize_secret_key_label(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "")


def _is_repeated_trivial_secret(value: str) -> bool:
    normalized = _normalize_secret_key_label(value)
    if len(set(normalized)) <= 1:
        return True

    return any(
        len(normalized) % len(token) == 0
        and normalized == token * (len(normalized) // len(token))
        for token in REPEATED_TRIVIAL_SECRET_TOKENS
    )


def _normalize_secret_key(value: str | None) -> str:
    if value is None:
        raise RuntimeError("SECRET_KEY is not configured or is insecure.")

    normalized = str(value).strip()
    normalized_label = _normalize_secret_key_label(normalized)

    if (
        not normalized
        or len(normalized) < MIN_SECRET_KEY_LENGTH
        or normalized_label in INSECURE_SECRET_KEY_VALUES
        or normalized_label in TRIVIAL_SECRET_KEY_VALUES
        or _is_repeated_trivial_secret(normalized)
    ):
        raise RuntimeError("SECRET_KEY is not configured or is insecure.")

    return normalized


def get_secret_key() -> str:
    return _normalize_secret_key(os.getenv("SECRET_KEY"))


def validate_runtime_security_settings() -> None:
    get_secret_key()


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

    DEBUG: bool = ENV_NORMALIZED != "production"

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

    TELEGRAM_ALERT_COOLDOWN_SECONDS: int = to_int(
        os.getenv("TELEGRAM_ALERT_COOLDOWN_SECONDS", 1800),
        1800,
        minimum=60
    )

    TELEGRAM_MAX_ALERTS_PER_BATCH: int = to_int(
        os.getenv("TELEGRAM_MAX_ALERTS_PER_BATCH", 5),
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

    @property
    def SECRET_KEY(self) -> str:
        return get_secret_key()

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
