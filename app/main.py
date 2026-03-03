from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.ranking import router as ranking_router
from app.market import router as market_router
from app.users import router as users_router
from app.plan_service import router as plan_router

# =====================================
# APP INIT
# =====================================

app = FastAPI(
    title="StockNewsBR API",
    version="1.0.0"
)

# =====================================
# CORS (Frontend futuro)
# =====================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # depois restringimos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================
# DATABASE AUTO CREATE
# =====================================

Base.metadata.create_all(bind=engine)

# =====================================
# ROUTERS
# =====================================

app.include_router(ranking_router)
app.include_router(market_router)
app.include_router(users_router)
app.include_router(plan_router)

# =====================================
# HEALTH CHECK
# =====================================

@app.get("/")
def health_check():
    return {
        "status": "StockNewsBR backend running 🚀",
        "version": "1.0.0"
    }