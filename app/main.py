from fastapi import FastAPI
from app.market import router as market_router
from app.users import router as auth_router
from app.database import engine
from app.models import Base

app = FastAPI(title="StockNewsBR – Inteligência de Mercado com IA")

# cria tabelas automaticamente
Base.metadata.create_all(bind=engine)

app.include_router(market_router)
app.include_router(auth_router)

@app.get("/")
def home():
    return {"status": "StockNewsBR backend running"}