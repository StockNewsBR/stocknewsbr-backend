from fastapi import FastAPI
from app.market import router as market_router

app = FastAPI(title="StockNewsBR Institutional Engine 🚀")

app.include_router(market_router)


@app.get("/")
def home():
    return {"status": "StockNewsBR backend running"}


from app.database import engine
from sqlalchemy import text

@app.get("/db-test")
def db_test():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        return {"database": "connected"}