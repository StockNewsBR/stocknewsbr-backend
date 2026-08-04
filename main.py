# =====================================================
# STOCKNEWSBR BACKEND API (V36 HARDENED)
# =====================================================

import importlib
import logging
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.ai.ai_market_pulse import market_pulse
from app.cache.snapshot_cache import (
    get_snapshot,
    get_snapshot_info,
    get_snapshot_signals,
)
from app.core.csrf import allowed_web_origins, csrf_rejection
from app.core.settings import (
    is_production_environment,
    validate_database_configuration,
    validate_runtime_security_settings,
)
from app.database import DATABASE_URL, Base, SessionLocal, engine
from app.database_schema import ensure_runtime_schema, validate_production_schema
from app.dependencies import require_internal_token
from app.services.media_service import ensure_media_root
from app.services.referrals import validate_referrals
from app.system.system_metrics import (
    increment_http_errors,
    increment_http_requests,
    provider_call_context,
    record_http_endpoint_latency,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("stocknewsbr.main")

# (module_path, attribute, critical).
#
# critical=True means the product is not servable without it: authentication, the
# system/health surface, the core signal + snapshot data product, news, the workspace
# endpoint both clients read, ranking, and the streaming transport. If one of these
# fails to import the process must not come up at all -- previously it booted with a
# WARNING and served /ping 200 while, say, app.auth was silently absent.
#
# critical=False means a broken import costs that feature and nothing else. These are
# the presentational app.web.* routes and secondary/social surfaces; taking the whole
# API down for a broken template route would be a worse outcome than losing it.
ROUTER_SPECS = [
    ("app.auth", "router", True),
    ("app.api.routes_opportunity", "router", False),
    ("app.api.routes_system", "router", True),
    ("app.api.routes_snapshot", "router", True),
    ("app.api.routes_signals", "router", True),
    ("app.api.routes_public_meta", "router", False),
    ("app.api.routes_public_market", "router", False),
    ("app.api.routes_public_market_live", "router", False),
    ("app.api.routes_internal", "router", True),
    ("app.api.routes_paper_trading", "router", False),
    ("app.api.routes_performance_intelligence", "router", False),
    ("app.api.routes_explainability", "router", False),
    ("app.api.api_market_routes", "router", False),
    ("app.api.market_routes", "router", False),
    ("app.api.routes_heatmap", "router", False),
    ("app.api.routes_narrative", "router", False),
    ("app.api.routes_radar", "router", True),
    ("app.api.routes_market_bar", "router", False),
    ("app.api.routes_activity", "router", False),
    ("app.api.routes_feed", "router", True),
    ("app.api.routes_likes", "router", False),
    ("app.api.routes_moderation", "router", False),
    ("app.api.routes_moderation_admin", "router", False),
    ("app.api.routes_media", "router", False),
    ("app.api.routes_push", "router", True),
    ("app.api.routes_poll", "router", False),
    ("app.api.routes_sentiment", "router", False),
    ("app.api.routes_social", "router", False),
    ("app.api.routes_chat", "router", False),
    ("app.api.routes_news", "router", True),
    ("app.api.routes_app_workspace", "router", True),
    ("app.api.stripe_webhook", "router", False),
    ("app.api.routes_ticker", "router", False),
    ("app.services.ranking", "router", True),
    ("app.system.stream_router", "router", True),
    ("app.web.routes_chart", "router", False),
    ("app.web.routes_dashboard", "router", False),
    ("app.web.routes_market_pulse", "router", False),
    ("app.web.routes_opportunities", "router", False),
    ("app.web.routes_radar", "router", False),
    ("app.web.routes_search", "router", False),
    ("app.web.routes_terminal", "router", False),
    ("app.web.routes_top_movers", "router", False),
    ("app.web.routes_watchlist", "router", False),
    ("app.web.routes_workspace", "router", False),
    ("app.web.routes_site", "router", False),
]

# Optional routers that failed to import, so health can report degradation instead of
# reporting a healthy process that is quietly missing endpoints.
DEGRADED_ROUTERS: list[str] = []

BACKGROUND_THREADS = {}
THREAD_LOCK = threading.RLock()
STOP_EVENT = threading.Event()
WORKERS_STARTED = False
WORKERS_LOCK = threading.Lock()


def _env_flag(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)

    if raw_value is None:
        return default

    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def _default_start_background_workers() -> bool:
    """Keep local API/web snappy; production can opt in explicitly."""
    return is_production_environment()


def _cors_origins():
    # Mission 31B: cookies ride on credentialed CORS, so a wildcard origin is
    # forbidden — the shared helper enforces exact origins.
    return allowed_web_origins()


def _create_tables_if_needed():
    try:
        import app.models  # noqa: F401

        if is_production_environment():
            validate_production_schema(engine)
        else:
            Base.metadata.create_all(bind=engine)
            ensure_runtime_schema(engine)
    except Exception:
        logger.exception("Database bootstrap failed")
        raise


def _seed_official_identities_if_needed():
    """Mission 31B.1: provision the canonical official account + bot at boot.

    Controlled startup path only — no public route, no Telegram/Push, the bot
    publishes nothing here. Fail-closed: if a non-canonical user already holds
    an official service email the seed raises a conflict, which we log and skip
    (a public account is NEVER promoted). Idempotent; safe on every boot.
    """
    if not _env_flag("SEED_OFFICIAL_IDENTITIES", True):
        return

    from app.services.official_identity_service import (
        OfficialIdentityConflictError,
        ensure_official_identities,
    )

    db = None
    try:
        db = SessionLocal()
        ensure_official_identities(db)
        logger.info("Official identities ensured")
    except OfficialIdentityConflictError:
        logger.error(
            "Official identity seed conflict — promotion skipped (fail-closed)"
        )
        if db is not None:
            db.rollback()
    except Exception:
        logger.exception(
            "Official identity seed failed — continuing without seeded identities"
        )
        if db is not None:
            db.rollback()
    finally:
        if db is not None:
            db.close()


def _safe_import_router(module_path: str, attribute: str, critical: bool = False):
    """Import one router. Critical failures are fatal; optional ones degrade.

    Returning None for everything is what let a broken app.auth boot a servable process
    whose only symptom was a WARNING indistinguishable from every other router's.
    """
    try:
        module = importlib.import_module(module_path)
        return getattr(module, attribute)
    except Exception as exc:
        if critical:
            logger.error("Critical router %s failed to import: %s", module_path, exc)
            raise RuntimeError(f"Critical router {module_path} failed to import: {exc}") from exc
        logger.warning("Skipping non-critical router %s: %s", module_path, exc)
        return None


def _include_routers(app: FastAPI):
    """Register every router. A critical failure propagates and aborts startup."""
    included = 0
    DEGRADED_ROUTERS.clear()

    for module_path, attribute, critical in ROUTER_SPECS:
        router = _safe_import_router(module_path, attribute, critical=critical)

        if router is None:
            DEGRADED_ROUTERS.append(module_path)
            continue

        app.include_router(router)
        included += 1

    if DEGRADED_ROUTERS:
        logger.warning(
            "Router bootstrap degraded | missing=%s", ",".join(DEGRADED_ROUTERS)
        )

    logger.info(
        "Router bootstrap completed | included=%s/%s", included, len(ROUTER_SPECS)
    )
    return included


def _start_thread(name: str, target, *args):
    with THREAD_LOCK:
        current = BACKGROUND_THREADS.get(name)

        if current and current.is_alive():
            return False

        thread = threading.Thread(
            target=target,
            args=args,
            name=name,
            daemon=True,
        )
        thread.start()
        BACKGROUND_THREADS[name] = thread
        return True


def referral_worker(stop_event: threading.Event):
    while not stop_event.is_set():
        db = None

        try:
            db = SessionLocal()
            validate_referrals(db)
        except Exception:
            logger.exception("Referral worker error")
        finally:
            if db is not None:
                db.close()

        stop_event.wait(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app

    global WORKERS_STARTED
    snapshot_worker_started = False
    quote_warmup_started = False

    STOP_EVENT.clear()
    logger.info(
        "Runtime bootstrap | python_executable=%s | python_version=%s",
        sys.executable,
        sys.version.replace("\n", " "),
    )
    if sys.version_info[:2] != (3, 11):
        logger.warning(
            "Runtime version mismatch | expected=3.11.x | current=%s.%s",
            sys.version_info.major,
            sys.version_info.minor,
        )
    validate_runtime_security_settings()
    logger.info("Security settings validated")
    validate_database_configuration(database_url=DATABASE_URL)
    logger.info("Database configuration validated")
    _create_tables_if_needed()
    _seed_official_identities_if_needed()

    with WORKERS_LOCK:
        if not WORKERS_STARTED:
            default_background_workers = _default_start_background_workers()
            engine_worker_enabled = _env_flag("START_ENGINE_WORKER", default_background_workers)
            # API-only/local processes still need a current global snapshot.
            # The engine remains the sole writer when it is enabled.
            snapshot_worker_enabled = _env_flag("START_SNAPSHOT_WORKER", not engine_worker_enabled)

            if engine_worker_enabled:
                from worker import start_worker

                started = _start_thread("stocknewsbr-engine-worker", start_worker, STOP_EVENT)
                logger.info("Engine worker thread started=%s", started)

            if _env_flag("START_REFERRAL_WORKER", True):
                started = _start_thread("stocknewsbr-referral-worker", referral_worker, STOP_EVENT)
                logger.info("Referral worker thread started=%s", started)

            if _env_flag("START_QUOTE_WARMUP", True):
                from app.system.quote_warmup import start_quote_warmup

                quote_warmup_started = bool(start_quote_warmup())
                logger.info("Quote warmup bootstrap requested | started=%s", quote_warmup_started)

            if snapshot_worker_enabled and not engine_worker_enabled:
                from app.system.snapshot_worker import start_snapshot_worker

                snapshot_worker_started = bool(start_snapshot_worker())
                logger.info("Snapshot worker bootstrap requested | started=%s", snapshot_worker_started)
            elif snapshot_worker_enabled and engine_worker_enabled:
                logger.info("Snapshot worker bootstrap skipped because engine worker is the active snapshot writer")

            if _env_flag("START_AI_WORKER", default_background_workers):
                from app.system.ai_worker import start_ai_worker

                started = _start_thread("stocknewsbr-ai-worker", start_ai_worker, STOP_EVENT)
                logger.info("AI worker thread started=%s", started)

            WORKERS_STARTED = True

    try:
        yield
    finally:
        STOP_EVENT.set()
        if snapshot_worker_started:
            try:
                from app.system.snapshot_worker import stop_snapshot_worker

                stop_snapshot_worker()
            except Exception:
                logger.exception("Snapshot worker shutdown failed")
        if quote_warmup_started:
            try:
                from app.system.quote_warmup import stop_quote_warmup

                stop_quote_warmup()
            except Exception:
                logger.exception("Quote warmup shutdown failed")

        with WORKERS_LOCK:
            WORKERS_STARTED = False


app = FastAPI(
    title="StockNewsBR API",
    version="3.3",
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=512)

@app.middleware("http")
async def csrf_origin_guard(request: Request, call_next):
    """Mission 31B CSRF protection (SameSite cookie + Origin/Referer check)."""
    rejection = csrf_rejection(request, _cors_origins())

    if rejection is not None:
        return rejection

    return await call_next(request)

app.mount(
    "/media",
    StaticFiles(directory=str(ensure_media_root())),
    name="media",
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.perf_counter()
    request_id = uuid4().hex
    increment_http_requests()
    response = None

    try:
        with provider_call_context("http"):
            response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request error on %s", request.url.path)
        increment_http_errors()
        duration_ms = (time.perf_counter() - start) * 1000
        response = JSONResponse(
            status_code=500,
            content={
                "detail": "internal_server_error",
                "request_id": request_id,
            },
        )
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
        response.headers["X-Request-Id"] = request_id
        route_match = request.scope.get("route")
        route = getattr(route_match, "path", None) if route_match is not None else None
        endpoint_key = route or "unmatched"
        record_http_endpoint_latency(endpoint_key, request.method, response.status_code, duration_ms / 1000)
        return response

    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
    response.headers["X-Request-Id"] = request_id

    if response.status_code >= 500:
        increment_http_errors()

    route_match = request.scope.get("route")
    route = getattr(route_match, "path", None) if route_match is not None else None
    endpoint_key = route or "unmatched"
    record_http_endpoint_latency(endpoint_key, request.method, response.status_code, duration_ms / 1000)

    return response


# Mission 31B: CORS is registered LAST so it wraps the whole middleware
# stack (outermost) and error responses from csrf_origin_guard / exception
# paths still carry Access-Control-Allow-Origin + credentials headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_include_routers(app)


@app.get("/opportunities")
def get_opportunities():
    preview_rows = []

    for signal in get_snapshot_signals(limit=5):
        preview_rows.append(
            {
                "ticker": signal.get("ticker") or signal.get("symbol"),
                "score": signal.get("score"),
                "signal": signal.get("signal"),
                "price": signal.get("price"),
            }
        )

    return {
        "preview": True,
        "count": len(preview_rows),
        "signals": preview_rows,
    }


@app.get("/market-pulse")
def get_market_pulse():
    return market_pulse(get_snapshot_signals())


@app.get("/spotlight")
def spotlight():
    signals = get_snapshot_signals(limit=1)
    return signals[0] if signals else {}


@app.get("/ping")
def ping():
    """Liveness plus router-bootstrap honesty.

    This used to return a flat 200 {"ping": "pong"} no matter how many routers had
    silently failed to import, which is precisely how missing endpoints went unnoticed.
    Critical routers now abort startup, so anything listed here is an optional router
    whose feature is unavailable while the rest of the API keeps serving.
    """
    degraded = list(DEGRADED_ROUTERS)
    return {
        "ping": "pong",
        "status": "degraded" if degraded else "ok",
        "routers_expected": len(ROUTER_SPECS),
        "routers_missing": degraded,
    }


@app.get("/debug/tables")
def debug_tables(_internal=Depends(require_internal_token)):
    del _internal

    query = (
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        if engine.url.drivername.startswith("sqlite")
        else "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )

    try:
        with engine.connect() as conn:
            result = conn.execute(text(query))
            return {"tables": [row[0] for row in result]}
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/")
def health():
    snapshot = get_snapshot()
    snapshot_info = get_snapshot_info()

    return {
        "status": "running",
        "service": "StockNewsBR backend",
        "version": "3.3",
        "engine": "V36",
        "signals": snapshot_info.get("signals", 0),
        "snapshot_updated_at": snapshot.get("updated_at"),
    }
