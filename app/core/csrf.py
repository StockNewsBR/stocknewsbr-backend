# ==========================================================
# STOCKNEWSBR CSRF ORIGIN GUARD (MISSION 31B)
# ==========================================================
# Cookie-authenticated mutable requests must present an Origin
# (or Referer) matching the exact allowed origins. Bearer-only
# clients (mobile app, telegram bot) are unaffected.

import os
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.settings import session_cookie_name

MUTABLE_HTTP_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_REJECTED_DETAIL = "csrf_origin_rejected"

DEFAULT_ALLOWED_WEB_ORIGINS = [
    "https://www.stocknewsbr.com",
    "https://stocknewsbr.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def allowed_web_origins() -> list[str]:
    """Exact browser origins allowed to use credentialed (cookie) requests.

    Single source for CORS, the CSRF guard and cookie-authenticated
    WebSocket handshakes. A wildcard entry is ignored — cookies must never
    ride on `*`.
    """
    raw_value = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        ",".join(DEFAULT_ALLOWED_WEB_ORIGINS),
    )
    origins = [item.strip() for item in raw_value.split(",") if item.strip() and item.strip() != "*"]
    return origins or list(DEFAULT_ALLOWED_WEB_ORIGINS)


def origin_from_header(value: str | None) -> str | None:
    raw = str(value or "").strip()

    if not raw:
        return None

    parsed = urlsplit(raw)

    if not parsed.scheme or not parsed.netloc:
        return None

    return f"{parsed.scheme}://{parsed.netloc}"


def csrf_rejection(request: Request, allowed_origins) -> JSONResponse | None:
    """Returns a 403 response when the request violates the CSRF policy."""
    if request.method not in MUTABLE_HTTP_METHODS:
        return None

    if session_cookie_name() not in request.cookies:
        return None

    origin = origin_from_header(request.headers.get("origin")) or origin_from_header(
        request.headers.get("referer")
    )

    if origin in set(allowed_origins or []):
        return None

    return JSONResponse(
        status_code=403,
        content={"detail": CSRF_REJECTED_DETAIL},
    )
