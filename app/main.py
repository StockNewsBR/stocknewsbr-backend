from fastapi import FastAPI
from app.market import router as market_router
from app.database import engine
from sqlalchemy import text

app = FastAPI(title="StockNewsBR Institutional Engine 🚀")

app.include_router(market_router)


@app.get("/")
def home():
    return {"status": "StockNewsBR backend running"}


@app.get("/db-test")
def db_test():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        return {"database": "connected"}


