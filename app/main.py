print("🚀 BUILD VERSION: ENGINE_V2_RUNNING")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import threading
import time

from app.database import engine, Base, SessionLocal
from app.ranking import router as ranking_router
from app.market import router as market_router
from app.stripe_webhook import router as stripe_router

from app import engine as ai_engine
from app import ranking
from app.ai_market_pulse import market_pulse
from app.engine import auto_update
from app.referrals import validate_referrals

from app.promo_router import router as promo_router
from app.admin_promo import router as admin_promo_router

# =====================================================
# APP INIT
# =====================================================

app = FastAPI(
    title="StockNewsBR API",
    version="1.0.0"
)


# =====================================================
# CORS
# =====================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================================================
# DATABASE
# =====================================================

Base.metadata.create_all(bind=engine)


# =====================================================
# ROUTERS
# =====================================================

app.include_router(ranking_router)
app.include_router(market_router)
app.include_router(stripe_router)

app.include_router(promo_router)
app.include_router(admin_promo_router)

# =====================================================
# REFERRAL WORKER
# =====================================================

def referral_worker():

    while True:

        db = SessionLocal()

        validate_referrals(db)

        time.sleep(3600)


threading.Thread(target=referral_worker, daemon=True).start()


# =====================================================
# API ENDPOINTS
# =====================================================

@app.get("/opportunities")
def get_opportunities():

    data = ai_engine.scan_market()

    ranked = ranking.rank_opportunities(data)

    return ranked


@app.get("/market-pulse")
def get_market_pulse():

    signals = ai_engine.collect_market_signals()

    return market_pulse(signals)


@app.get("/spotlight")
def opportunity_spotlight():

    data = ai_engine.scan_market()

    ranked = ranking.rank_opportunities(data)

    if ranked:
        return ranked[0]

    return {}


# =====================================================
# DEBUG
# =====================================================

@app.get("/ping")
def ping():
    return {"ping": "pong"}


@app.get("/debug/tables")
def debug_tables():

    with engine.connect() as conn:

        result = conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public';"
        ))

        return {"tables": [row[0] for row in result]}


# =====================================================
# HEALTH CHECK
# =====================================================

@app.get("/")
def health_check():

    return {
        "status": "StockNewsBR backend running 🚀"
    }


# =====================================================
# START ENGINE
# =====================================================

threading.Thread(target=auto_update, daemon=True).start()