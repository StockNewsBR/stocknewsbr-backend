# ==========================================================
# STOCKNEWSBR CSRF ORIGIN GUARD (MISSION 31B)
# ==========================================================
# Cookie-authenticated mutable requests must present an Origin
# (or Referer) matching the exact allowed origins. Bearer-only
# clients (mobile app, telegram bot) are unaffected.

import os
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.settings import _current_env_normalized, session_cookie_name

MUTABLE_HTTP_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_REJECTED_DETAIL = "csrf_origin_rejected"
SESSION_ORIGIN_REJECTED_DETAIL = "csrf_session_origin_rejected"
SESSION_ORIGIN_MISSING_DETAIL = "csrf_session_origin_missing"

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


def enforce_session_establishment_origin(request: Request | None) -> None:
    """Guard endpoints that CREATE a browser session cookie (the web channel of
    login/register/verify-otp) against login CSRF / session fixation.

    Client separation is by CHANNEL, not by header presence: this guard is only
    invoked for the ``web`` (cookie) channel — see ``_issue_session``. Mobile/API
    clients log in on the ``app`` channel with a bearer token and never receive
    a cookie, so they never reach this guard.

    Within the web channel:
      * A present ``Origin`` (or ``Referer``) MUST match the exact allowlist; a
        foreign origin — the cross-site form-POST vector — is rejected.
      * An ABSENT ``Origin`` and ``Referer`` fails CLOSED in production: a real
        browser web login always sends at least one, so their absence is a
        cross-site / non-browser attempt. In dev/test it is allowed so local
        tooling and the test client (which sends neither header) keep working.
    """
    if request is None:
        return

    origin = origin_from_header(request.headers.get("origin")) or origin_from_header(
        request.headers.get("referer")
    )

    if origin is not None:
        if origin in set(allowed_web_origins()):
            return
        raise HTTPException(status_code=403, detail=SESSION_ORIGIN_REJECTED_DETAIL)

    # No Origin and no Referer on the web cookie channel: fail closed in prod.
    if _current_env_normalized() == "production":
        raise HTTPException(status_code=403, detail=SESSION_ORIGIN_MISSING_DETAIL)
