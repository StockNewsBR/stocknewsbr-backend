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
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.ai.ai_market_pulse import market_pulse
from app.cache.snapshot_cache import get_snapshot, get_snapshot_info, get_snapshot_signals
from app.database import Base, SessionLocal, engine
from app.database_schema import ensure_runtime_schema
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

ROUTER_SPECS = [
    ("app.auth", "router"),
    ("app.api.routes_opportunity", "router"),
    ("app.api.routes_system", "router"),
    ("app.api.routes_snapshot", "router"),
    ("app.api.routes_signals", "router"),
    ("app.api.routes_public_meta", "router"),
    ("app.api.routes_public_market", "router"),
    ("app.api.routes_public_market_live", "router"),
    ("app.api.routes_internal", "router"),
    ("app.api.api_market_routes", "router"),
    ("app.api.market_routes", "router"),
    ("app.api.routes_heatmap", "router"),
    ("app.api.routes_narrative", "router"),
    ("app.api.routes_radar", "router"),
    ("app.api.routes_market_bar", "router"),
    ("app.api.routes_activity", "router"),
    ("app.api.routes_feed", "router"),
    ("app.api.routes_likes", "router"),
    ("app.api.routes_moderation", "router"),
    ("app.api.routes_moderation_admin", "router"),
    ("app.api.routes_media", "router"),
    ("app.api.routes_push", "router"),
    ("app.api.routes_poll", "router"),
    ("app.api.routes_sentiment", "router"),
    ("app.api.routes_social", "router"),
    ("app.api.routes_chat", "router"),
    ("app.api.routes_news", "router"),
    ("app.api.routes_app_workspace", "router"),
    ("app.api.stripe_webhook", "router"),
    ("app.api.routes_ticker", "router"),
    ("app.services.ranking", "router"),
    ("app.system.stream_router", "router"),
    ("app.web.routes_chart", "router"),
    ("app.web.routes_dashboard", "router"),
    ("app.web.routes_market_pulse", "router"),
    ("app.web.routes_opportunities", "router"),
    ("app.web.routes_radar", "router"),
    ("app.web.routes_search", "router"),
    ("app.web.routes_terminal", "router"),
    ("app.web.routes_top_movers", "router"),
    ("app.web.routes_watchlist", "router"),
    ("app.web.routes_workspace", "router"),
    ("app.web.routes_site", "router"),
]

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
    return os.getenv("ENV", "development").strip().lower() == "production"


def _cors_origins():
    raw_value = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "https://www.stocknewsbr.com,https://stocknewsbr.com,http://localhost:3000,http://127.0.0.1:3000",
    )
    origins = [item.strip() for item in raw_value.split(",") if item.strip()]
    return origins or ["*"]


def _create_tables_if_needed():
    environment = os.getenv("ENV", "development").lower()

    try:
        import app.models  # noqa: F401

        if environment != "production" or engine.url.drivername.startswith("sqlite"):
            Base.metadata.create_all(bind=engine)

        ensure_runtime_schema(engine)
    except Exception:
        logger.exception("Database bootstrap failed")
        raise


def _safe_import_router(module_path: str, attribute: str):
    try:
        module = importlib.import_module(module_path)
        return getattr(module, attribute)
    except Exception as exc:
        logger.warning("Skipping router %s: %s", module_path, exc)
        return None


def _include_routers(app: FastAPI):
    included = 0

    for module_path, attribute in ROUTER_SPECS:
        router = _safe_import_router(module_path, attribute)

        if router is None:
            continue

        app.include_router(router)
        included += 1

    logger.info("Router bootstrap completed | included=%s", included)


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
    _create_tables_if_needed()

    with WORKERS_LOCK:
        if not WORKERS_STARTED:
            default_background_workers = _default_start_background_workers()
            engine_worker_enabled = _env_flag("START_ENGINE_WORKER", default_background_workers)
            snapshot_worker_enabled = _env_flag("START_SNAPSHOT_WORKER", False)

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=512)
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
        route = getattr(request.scope.get("route"), "path", None) or request.url.path
        record_http_endpoint_latency(route, request.method, response.status_code, duration_ms / 1000)
        return response

    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
    response.headers["X-Request-Id"] = request_id

    if response.status_code >= 500:
        increment_http_errors()

    route = getattr(request.scope.get("route"), "path", None) or request.url.path
    record_http_endpoint_latency(route, request.method, response.status_code, duration_ms / 1000)

    return response


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
    return {"ping": "pong"}


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
