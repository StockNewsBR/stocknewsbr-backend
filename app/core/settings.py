# =====================================================
# STOCKNEWSBR GLOBAL SETTINGS
# =====================================================

import hashlib
import hmac
import os
import logging
from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

logger = logging.getLogger("stocknewsbr.settings")

# =====================================================
# LOAD ENV (SAFE)
# =====================================================

PRODUCTION_ENVIRONMENTS = frozenset({"prod", "production"})
_PROCESS_ENV = str(os.getenv("ENV") or "").strip().lower()

if _PROCESS_ENV not in PRODUCTION_ENVIRONMENTS:
    load_dotenv()


ENV = str(os.getenv("ENV", "development")).strip() or "development"
ENV_NORMALIZED = ENV.lower()
MIN_SECRET_KEY_LENGTH = 32
DEFAULT_DATABASE_URL = "sqlite:///./stocknews.db"

DATABASE_PLACEHOLDER_COMPONENTS = frozenset(
    {
        "change_me",
        "change_this",
        "changeme",
        "database",
        "dbname",
        "example",
        "example.com",
        "host",
        "hostname",
        "password",
        "secret",
        "user",
        "username",
        "your_database",
        "your_host",
        "your_password",
        "your_user",
    }
)


def get_runtime_environment(value: str | None = None) -> str:
    configured = value if value is not None else os.getenv("ENV", ENV)
    return str(configured or "development").strip().lower() or "development"


def is_production_environment(value: str | None = None) -> bool:
    return get_runtime_environment(value) in PRODUCTION_ENVIRONMENTS


def get_database_url(value: str | None = None) -> str:
    configured = value if value is not None else os.getenv("DATABASE_URL")
    normalized = str(configured or "").strip()
    return normalized or DEFAULT_DATABASE_URL


def _database_component_is_placeholder(value: str | None) -> bool:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if not normalized:
        return False
    if normalized in DATABASE_PLACEHOLDER_COMPONENTS:
        return True
    if "${" in normalized and "}" in normalized:
        return True
    if "{{" in normalized and "}}" in normalized:
        return True
    return "<" in normalized and ">" in normalized


def validate_database_configuration(
    *,
    environment: str | None = None,
    database_url: str | None = None,
) -> str:
    configured = database_url if database_url is not None else os.getenv("DATABASE_URL")
    normalized = str(configured or "").strip()

    if not is_production_environment(environment):
        return normalized or DEFAULT_DATABASE_URL

    if not normalized:
        raise RuntimeError("DATABASE_URL_REQUIRED_FOR_PRODUCTION")

    try:
        parsed = make_url(normalized)
    except (ArgumentError, TypeError, ValueError) as exc:
        raise RuntimeError("DATABASE_URL_INVALID_FOR_PRODUCTION") from exc

    if parsed.get_backend_name() != "postgresql":
        raise RuntimeError("POSTGRESQL_REQUIRED_FOR_PRODUCTION")

    if parsed.drivername not in {"postgresql", "postgresql+psycopg2"}:
        raise RuntimeError("SYNC_POSTGRESQL_DRIVER_REQUIRED_FOR_PRODUCTION")

    components = (parsed.username, parsed.password, parsed.host, parsed.database)
    if any(not str(component or "").strip() for component in components):
        raise RuntimeError("DATABASE_URL_INCOMPLETE_FOR_PRODUCTION")
    if any(_database_component_is_placeholder(component) for component in components):
        raise RuntimeError("DATABASE_URL_PLACEHOLDER_FORBIDDEN_IN_PRODUCTION")

    return normalized


DATABASE_URL = get_database_url()

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


# =====================================================
# MISSION 31B - AUTH / OTP / SESSION SETTINGS
# =====================================================

MIN_OTP_PEPPER_LENGTH = 16

OTP_PEPPER_PLACEHOLDER_VALUES = frozenset(
    {
        "change_this_pepper",
        "changeme",
        "change_me",
        "default",
        "pepper",
        "otp_pepper",
        "secret",
        "test_pepper",
        "dev_pepper",
    }
)


def _normalize_otp_pepper(value: str | None) -> str:
    normalized = str(value or "").strip()
    normalized_label = _normalize_secret_key_label(normalized)

    if (
        not normalized
        or len(normalized) < MIN_OTP_PEPPER_LENGTH
        or normalized_label in OTP_PEPPER_PLACEHOLDER_VALUES
        or (normalized.startswith("<") and normalized.endswith(">"))
        or len(set(normalized_label)) <= 3
    ):
        return ""

    return normalized


def get_otp_pepper() -> str:
    configured = _normalize_otp_pepper(os.getenv("OTP_PEPPER"))

    if configured:
        return configured

    if is_production_environment():
        raise RuntimeError("OTP_PEPPER_NOT_CONFIGURED")

    # Non-production only: deterministic pepper derived from the mandatory
    # SECRET_KEY so local/dev/test never operate with an empty pepper.
    return hmac.new(
        get_secret_key().encode("utf-8"),
        b"stocknewsbr-otp-pepper-v1",
        hashlib.sha256,
    ).hexdigest()


def _current_env_normalized() -> str:
    return str(os.getenv("ENV", ENV)).strip().lower() or "development"


def _to_positive_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(str(os.getenv(name, default)).strip())
    except Exception:
        return default
    return value if value >= minimum else default


def login_code_expiry_seconds() -> int:
    return _to_positive_int("LOGIN_CODE_EXPIRY_SECONDS", 600, minimum=60)


def login_code_max_attempts() -> int:
    return _to_positive_int("LOGIN_CODE_MAX_ATTEMPTS", 5)


def login_code_max_sends_per_email() -> int:
    return _to_positive_int("LOGIN_CODE_MAX_SENDS_PER_EMAIL", 3)


def login_code_send_window_seconds() -> int:
    return _to_positive_int("LOGIN_CODE_SEND_WINDOW_SECONDS", 900, minimum=60)


def login_code_resend_cooldown_seconds() -> int:
    # 0 disables the cooldown (used by controlled test environments).
    return _to_positive_int("LOGIN_CODE_RESEND_COOLDOWN_SECONDS", 60, minimum=0)


def login_code_max_sends_per_ip() -> int:
    return _to_positive_int("LOGIN_CODE_MAX_SENDS_PER_IP", 10)


def session_cookie_name() -> str:
    configured = str(os.getenv("SESSION_COOKIE_NAME", "")).strip()

    if configured:
        return configured

    return "__Host-snb_session" if is_production_environment() else "snb_session"


def session_cookie_secure() -> bool:
    raw = os.getenv("SESSION_COOKIE_SECURE")

    if raw is None:
        return is_production_environment()

    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def session_cookie_samesite() -> str:
    value = str(os.getenv("SESSION_COOKIE_SAMESITE", "lax")).strip().lower()
    return value if value in {"lax", "strict"} else "lax"


def auth_email_test_mailbox_path() -> str:
    """Test-only OTP capture mailbox. Must never be active in production."""
    return str(os.getenv("AUTH_EMAIL_TEST_MAILBOX", "")).strip()


def validate_runtime_security_settings() -> None:
    get_secret_key()

    if is_production_environment():
        configured_pepper = _normalize_otp_pepper(os.getenv("OTP_PEPPER"))
        if not configured_pepper:
            raise RuntimeError("OTP_PEPPER_NOT_CONFIGURED")

        if auth_email_test_mailbox_path():
            raise RuntimeError("AUTH_EMAIL_TEST_MAILBOX_FORBIDDEN_IN_PRODUCTION")

        # Mission 31B: the session cookie must never ship without Secure in
        # production, even through explicit misconfiguration.
        if not session_cookie_secure():
            raise RuntimeError("SESSION_COOKIE_SECURE_REQUIRED_IN_PRODUCTION")


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

    DEBUG: bool = not is_production_environment(ENV_NORMALIZED)

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

    DATABASE_URL: str = DATABASE_URL

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
