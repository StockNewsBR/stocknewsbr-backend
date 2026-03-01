from fastapi import FastAPI
from app.market import router as market_router
from app.auth import router as auth_router

app = FastAPI(title="StockNewsBR – Inteligência de Mercado com IA")

app.include_router(market_router)
app.include_router(auth_router)

@app.get("/")
def home():
    return {"status": "StockNewsBR backend running"}