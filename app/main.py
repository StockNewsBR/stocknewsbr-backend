print("🚀 BUILD VERSION: ENGINE_V2_RUNNING")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import threading

from app.database import engine, Base
from app.ranking import router as ranking_router
from app.market import router as market_router

from app.engine import auto_update

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
# HEALTH
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