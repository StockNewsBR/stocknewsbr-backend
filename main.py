from fastapi import FastAPI, Query
import yfinance as yf
import pandas as pd
from datetime import datetime
import threading
import time

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, DateTime, desc
from sqlalchemy.orm import declarative_base, sessionmaker

# ==========================================
# FASTAPI
# ==========================================

app = FastAPI(title="StockNewsBR Institutional Engine 🚀")

# ==========================================
# DATABASE
# ==========================================

DATABASE_URL = "sqlite:///stocknewsbr.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

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

Base.metadata.create_all(engine)

# ==========================================
# CONFIG
# ==========================================

UPDATE_INTERVAL = 60
TELEGRAM_TOKEN = "8663741789:AAHSEGiO5OFGhzbVA2MzqxPd-npqmIGYX0s"

SYMBOLS = [
    "PETR4.SA","VALE3.SA","ITUB4.SA","BBDC4.SA",
    "BBAS3.SA","ABEV3.SA","B3SA3.SA","SUZB3.SA",
    "WEGE3.SA","GGBR4.SA","CSNA3.SA","RADL3.SA",
    "AAPL34.SA","AMZO34.SA","MELI34.SA","MSFT34.SA",
    "NVDC34.SA","PFIZ34.SA"
]

CACHE = {}
LAST_UPDATE = None

# ==========================================
# SAVE IF CHANGED
# ==========================================

def save_if_changed(result):
    db = SessionLocal()

    last = (
        db.query(Signal)
        .filter(Signal.symbol == result["symbol"])
        .order_by(desc(Signal.created_at))
        .first()
    )

    should_save = False

    if not last:
        should_save = True
    else:
        if (
            last.score != result["score"] or
            last.trend != result["trend"] or
            last.breakout != result["breakout"]
        ):
            should_save = True

    if should_save:
        db.add(Signal(**result))
        db.commit()

    db.close()

# ==========================================
# ENGINE
# ==========================================

def calculate_score(ticker):
    try:
        df = yf.download(
            ticker,
            period="6mo",
            interval="1d",
            auto_adjust=True,
            progress=False
        )

        if df is None or df.empty or len(df) < 60:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df["Close"]
        volume = df["Volume"]

        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss
        rsi_val = float((100 - (100 / (1 + rs))).iloc[-1])

        ema9 = close.ewm(span=9, adjust=False).mean()
        ema21 = close.ewm(span=21, adjust=False).mean()
        ema9_val = float(ema9.iloc[-1])
        ema21_val = float(ema21.iloc[-1])

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_val = float((ema12 - ema26).iloc[-1])

        returns = close.pct_change()
        volatility = returns.rolling(20).std()
        vol_now = float(volatility.iloc[-1])
        vol_prev = float(volatility.iloc[-5])

        avg_volume = volume.rolling(20).mean()
        volume_ratio = float(volume.iloc[-1] / avg_volume.iloc[-1])

        highest_20 = close.rolling(20).max().iloc[-2]
        breakout = bool(close.iloc[-1] > highest_20)

        score = 0
        if 55 < rsi_val < 70: score += 20
        if macd_val > 0: score += 20
        if ema9_val > ema21_val: score += 20
        if vol_now > vol_prev: score += 15
        if volume_ratio > 1.5: score += 15
        if breakout: score += 10

        trend = "UPTREND" if ema9_val > ema21_val else "DOWNTREND"

        result = {
            "symbol": ticker,
            "score": score,
            "trend": trend,
            "rsi": round(rsi_val,2),
            "macd": round(macd_val,4),
            "volatility": round(vol_now,4),
            "volume_spike": round(volume_ratio,2),
            "breakout": breakout
        }

        save_if_changed(result)

        return result

    except Exception as e:
        print("Erro:", e)
        return None

# ==========================================
# UPDATE LOOP
# ==========================================

def update_cache():
    global CACHE, LAST_UPDATE

    print("⚡ Updating engine...")

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

# ==========================================
# TELEGRAM
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 StockNewsBR Online!\nUse /acao PETR4")

async def acao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("Use: /acao PETR4")
        return

    ticker = context.args[0].upper() + ".SA"
    data = CACHE.get(ticker)

    if not data:
        await update.message.reply_text("Ativo não encontrado.")
        return

    await update.message.reply_text(str(data))

def run_bot():
    bot = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CommandHandler("acao", acao))
    bot.run_polling()

threading.Thread(target=run_bot, daemon=True).start()

# ==========================================
# ENDPOINTS
# ==========================================

@app.get("/ranking")
def ranking():
    return {"data": list(CACHE.values()), "updated_at": LAST_UPDATE}

@app.get("/ranking/top")
def ranking_top(min_score: int = Query(50)):
    filtered = [v for v in CACHE.values() if v["score"] >= min_score]
    return {"data": filtered, "updated_at": LAST_UPDATE}

@app.get("/signals/latest")
def signals_latest(limit: int = 20):
    db = SessionLocal()
    results = db.query(Signal).order_by(desc(Signal.created_at)).limit(limit).all()
    db.close()

    return [
        {
            "symbol": r.symbol,
            "score": r.score,
            "trend": r.trend,
            "rsi": r.rsi,
            "created_at": r.created_at
        }
        for r in results
    ]

@app.get("/signals/history")
def signal_history(symbol: str):
    db = SessionLocal()
    results = db.query(Signal).filter(Signal.symbol == symbol).order_by(desc(Signal.created_at)).limit(100).all()
    db.close()

    return [
        {
            "symbol": r.symbol,
            "score": r.score,
            "trend": r.trend,
            "rsi": r.rsi,
            "created_at": r.created_at
        }
        for r in results
    ]