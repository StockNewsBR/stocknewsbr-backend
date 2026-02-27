from fastapi import FastAPI, Query
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import threading
import time
from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, DateTime, desc
from sqlalchemy.orm import declarative_base, sessionmaker

# ==================================================
# FASTAPI
# ==================================================

app = FastAPI(title="StockNewsBR Institutional Engine 🚀")

# ==================================================
# DATABASE
# ==================================================

DATABASE_URL = "sqlite:///stocknewsbr.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ==================================================
# MODELS
# ==================================================

class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String)
    score = Column(Integer)
    trend = Column(String)
    rsi = Column(Float)
    macd = Column(Float)
    volatility = Column(Float)
    volume_spike = Column(Float)
    breakout = Column(Boolean)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True)
    phone_number = Column(String, unique=True, nullable=True)
    is_verified = Column(Boolean, default=False)
    plan = Column(String, default="basic")  # basic | trial | premium
    trial_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)

# ==================================================
# USER MANAGEMENT
# ==================================================

def get_or_create_user(telegram_id: str):
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=telegram_id).first()

    if not user:
        trial_expiry = datetime.utcnow() + timedelta(days=90)

        user = User(
            telegram_id=telegram_id,
            plan="trial",
            trial_expires_at=trial_expiry,
            is_verified=False
        )

        db.add(user)
        db.commit()

    db.close()
    return user


def check_and_update_plan(user: User):
    db = SessionLocal()

    if user.plan == "trial" and user.trial_expires_at:
        if datetime.utcnow() > user.trial_expires_at:
            user.plan = "basic"
            db.merge(user)
            db.commit()

    db.close()


# ==================================================
# CONFIG
# ==================================================

UPDATE_INTERVAL = 60

SYMBOLS = [
    "PETR4.SA","VALE3.SA","ITUB4.SA","BBDC4.SA",
    "BBAS3.SA","ABEV3.SA","B3SA3.SA","SUZB3.SA",
    "WEGE3.SA","GGBR4.SA","CSNA3.SA","RADL3.SA",
    "AAPL34.SA","AMZO34.SA","MELI34.SA","MSFT34.SA",
    "NVDC34.SA","PFIZ34.SA"
]

CACHE = {}
LAST_UPDATE = None

# ==================================================
# SAVE IF CHANGED
# ==================================================

def save_if_changed(result):
    db = SessionLocal()

    last = (
        db.query(Signal)
        .filter(Signal.symbol == result["symbol"])
        .order_by(desc(Signal.created_at))
        .first()
    )

    if not last or (
        last.score != result["score"] or
        last.trend != result["trend"] or
        last.breakout != result["breakout"]
    ):
        db.add(Signal(**result))
        db.commit()

    db.close()

# ==================================================
# ENGINE
# ==================================================

def calculate_score(ticker):
    try:
        df = yf.download(
            ticker,
            period="6mo",
            interval="1d",
            auto_adjust=True,
            progress=False
        )

        if df is None or df.empty or len(df) < 200:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df["Close"]

        ema21 = close.ewm(span=21, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        ema200 = close.ewm(span=200, adjust=False).mean()

        structure_ok = ema21.iloc[-1] > ema50.iloc[-1] > ema200.iloc[-1]

        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss
        rsi = (100 - (100 / (1 + rs))).iloc[-1]

        highest_20 = close.rolling(20).max().iloc[-2]
        breakout = close.iloc[-1] > highest_20

        score = 0
        if structure_ok: score += 40
        if breakout: score += 30
        if 55 < rsi < 70: score += 20

        trend = "UPTREND" if structure_ok else "DOWNTREND"

        result = {
            "symbol": ticker,
            "score": int(score),
            "trend": trend,
            "rsi": round(float(rsi), 2),
            "macd": 0.0,
            "volatility": 0.0,
            "volume_spike": 0.0,
            "breakout": bool(breakout)
        }

        save_if_changed(result)
        return result

    except Exception as e:
        print("Erro:", e)
        return None

# ==================================================
# UPDATE LOOP
# ==================================================

def update_cache():
    global CACHE, LAST_UPDATE

    results = []

    for symbol in SYMBOLS:
        result = calculate_score(symbol)
        if result:
            results.append(result)

    if results:
        results.sort(key=lambda x: x["score"], reverse=True)
        CACHE = {item["symbol"]: item for item in results}
        LAST_UPDATE = datetime.now().strftime("%H:%M:%S")


def auto_update():
    while True:
        update_cache()
        time.sleep(UPDATE_INTERVAL)


threading.Thread(target=auto_update, daemon=True).start()

# ==================================================
# ENDPOINTS
# ==================================================

@app.post("/verify")
def verify_user(telegram_id: str, phone_number: str):
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=telegram_id).first()

    if not user:
        db.close()
        return {"error": "Usuário não encontrado"}

    user.phone_number = phone_number
    user.is_verified = True

    db.commit()
    db.close()

    return {"status": "verified"}


@app.get("/user/status")
def user_status(telegram_id: str):
    db = SessionLocal()
    user = db.query(User).filter_by(telegram_id=telegram_id).first()

    if not user:
        db.close()
        return {"error": "User not found"}

    days_left = None

    if user.trial_expires_at:
        delta = user.trial_expires_at - datetime.utcnow()
        days_left = max(delta.days, 0)

    db.close()

    return {
        "plan": user.plan,
        "is_verified": user.is_verified,
        "days_left": days_left
    }


@app.get("/ranking")
def ranking(telegram_id: str = Query(...)):
    user = get_or_create_user(telegram_id)
    check_and_update_plan(user)

    if not user.is_verified:
        return {
            "error": "verification_required",
            "message": "Envie seu número para ativar o Premium Trial."
        }

    if user.plan == "basic":
        return {
            "error": "premium_required",
            "message": "🔔 Seu período Premium expirou. Assine o Plano Premium."
        }

    return {"data": list(CACHE.values()), "updated_at": LAST_UPDATE}


@app.get("/ranking/top")
def ranking_top(
    telegram_id: str = Query(...),
    min_score: int = Query(50)
):
    user = get_or_create_user(telegram_id)
    check_and_update_plan(user)

    if not user.is_verified:
        return {
            "error": "verification_required",
            "message": "Verificação obrigatória."
        }

    if user.plan == "basic":
        return {
            "error": "premium_required",
            "message": "Plano Básico não possui acesso ao ranking avançado."
        }

    filtered = [v for v in CACHE.values() if v["score"] >= min_score]
    return {"data": filtered, "updated_at": LAST_UPDATE}