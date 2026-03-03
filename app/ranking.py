from fastapi import APIRouter, Depends
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from app.dependencies import require_active_plan
from app.config import SYMBOLS

router = APIRouter(
    prefix="/ranking",
    tags=["Ranking"]
)


def calculate_score(symbol: str):
    df = yf.download(symbol, period="5d", interval="5m")
    if df.empty:
        return None

    df["RSI"] = ta.rsi(df["Close"], length=14)
    macd = ta.macd(df["Close"])
    df = pd.concat([df, macd], axis=1)

    rsi = df["RSI"].iloc[-1]

    macd_col = [c for c in df.columns if "MACD_" in c and "MACDs" not in c][0]
    signal_col = [c for c in df.columns if "MACDs_" in c][0]

    macd_val = df[macd_col].iloc[-1]
    macd_signal = df[signal_col].iloc[-1]

    score = 0

    if rsi < 30:
        score += 1
    if macd_val > macd_signal:
        score += 1

    trend = "UPTREND" if score >= 1 else "DOWNTREND"

    return {
        "symbol": symbol,
        "score": score,
        "trend": trend,
        "rsi": round(float(rsi), 2),
        "breakout": macd_val > macd_signal
    }


@router.get("")
def get_ranking(current_user=Depends(require_active_plan)):

    results = []

    for symbol in SYMBOLS:
        data = calculate_score(symbol)
        if data:
            results.append(data)

    results = sorted(results, key=lambda x: x["score"], reverse=True)

    return {"data": results}


@router.get("/top")
def get_top(min_score: int = 1, current_user=Depends(require_active_plan)):

    results = []

    for symbol in SYMBOLS:
        data = calculate_score(symbol)
        if data and data["score"] >= min_score:
            results.append(data)

    results = sorted(results, key=lambda x: x["score"], reverse=True)

    return {"data": results}