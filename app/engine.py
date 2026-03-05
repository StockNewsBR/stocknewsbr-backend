import yfinance as yf
import pandas as pd
from datetime import datetime
import time

# ==========================================
# CONFIG
# ==========================================

UPDATE_INTERVAL = 900  # 15 minutos

SYMBOLS = [


# =========================
# B3 - AÇÕES
# =========================

"PETR3.SA","PETR4.SA","VALE3.SA","ITUB4.SA",
"BBDC3.SA","BBDC4.SA","BBAS3.SA","B3SA3.SA",

"MGLU3.SA","LREN3.SA","PRIO3.SA","CSNA3.SA",
"GGBR4.SA","USIM5.SA","SUZB3.SA","KLBN11.SA",

"JHSF3.SA","MULT3.SA","CYRE3.SA","EZTC3.SA",
"CVCB3.SA","AZUL4.SA","GOLL4.SA",

"NTCO3.SA","HAPV3.SA","RDOR3.SA",

"VIVT3.SA","TIMS3.SA",

"EMBR3.SA","WEGE3.SA",

"BRFS3.SA","JBSS3.SA",

"MRVE3.SA",

"CPLE6.SA","CMIG4.SA","ELET3.SA","ELET6.SA",
"ENBR3.SA","TAEE11.SA","TRPL4.SA",

"YDUQ3.SA",

# =========================
# BDRs
# =========================

"AAPL34.SA","MSFT34.SA","AMZO34.SA","GOGL34.SA",
"FBOK34.SA","TSLA34.SA","BERK34.SA","NFLX34.SA",
"NVDC34.SA","JPMN34.SA","VISA34.SA",

"MCDC34.SA","DISB34.SA","PYPL34.SA",

"ADID34.SA","NKE34.SA",

"ORCL34.SA","INTC34.SA",

"PFE34.SA","KO34.SA",

# =========================
# BDRs adicionais
# =========================

"A1MD34.SA","ADBE34.SA","AIRB34.SA",
"B1NT34.SA","CMCS34.SA","COC34.SA",
"COW34.SA","EXXO34.SA","GMCO34.SA",
"GSGI34.SA","JNJB34.SA","JPMC34.SA",
"M1RN34.SA","MSCD34.SA","MUTC34.SA",
"NIKE34.SA","PGCO34.SA","SSFO34.SA",
"WFCO34.SA"


]

CACHE = {}
LAST_UPDATE = None


# ==========================================
# INDICATORS
# ==========================================

def calculate_indicators(df):

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()

    macd = ema12 - ema26

    avg_volume = volume.rolling(20).mean()
    volume_ratio = volume / avg_volume

    breakout = close.iloc[-1] > close.rolling(20).max().iloc[-2]

    return {
        "rsi": float(rsi.iloc[-1]),
        "ema9": float(ema9.iloc[-1]),
        "ema21": float(ema21.iloc[-1]),
        "macd": float(macd.iloc[-1]),
        "volume_ratio": float(volume_ratio.iloc[-1]),
        "breakout": bool(breakout),
    }


# ==========================================
# SCORE ENGINE
# ==========================================

def calculate_score(ticker):

    try:

        df = yf.download(
            ticker,
            period="5d",
            interval="15m",
            auto_adjust=True,
            progress=False
        )

        if df is None or df.empty or len(df) < 50:
            return None

        indicators = calculate_indicators(df)

        score = 0

        if 55 < indicators["rsi"] < 70:
            score += 20

        if indicators["macd"] > 0:
            score += 20

        if indicators["ema9"] > indicators["ema21"]:
            score += 20

        if indicators["volume_ratio"] > 1.5:
            score += 20

        if indicators["breakout"]:
            score += 20

        trend = "UPTREND" if indicators["ema9"] > indicators["ema21"] else "DOWNTREND"

        return {
            "symbol": ticker,
            "score": score,
            "trend": trend,
            "rsi": round(indicators["rsi"],2),
            "macd": round(indicators["macd"],4),
            "volume_spike": round(indicators["volume_ratio"],2),
            "breakout": indicators["breakout"]
        }

    except Exception as e:
        print("Erro:", ticker, e)
        return None


# ==========================================
# ENGINE LOOP
# ==========================================

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

        print("Engine updated", LAST_UPDATE)


def auto_update():

    while True:

        update_cache()

        time.sleep(UPDATE_INTERVAL)