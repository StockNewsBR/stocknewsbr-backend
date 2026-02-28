from fastapi import FastAPI

from app.market import router as market_router

app = FastAPI(title="StockNewsBR Institutional Engine 🚀")

app.include_router(market_router)


@app.get("/")
def home():
    return {"status": "StockNewsBR backend running"}
