# =====================================================
# STOCKNEWSBR AI MARKET RADAR V2
# =====================================================

import logging
from datetime import datetime

logger = logging.getLogger("stocknewsbr.market_radar_v2")


# =====================================================
# SAFE DATA CHECK
# =====================================================

def valid_df(df):

    try:

        if df is None:
            return False

        if len(df) < 25:
            return False

        required = ["High", "Low", "Close", "Volume"]

        for col in required:

            if col not in df.columns:
                return False

        return True

    except Exception:

        return False


# =====================================================
# LIQUIDITY SWEEP
# =====================================================

def detect_liquidity_sweep(df):

    try:

        prev_low = df["Low"].iloc[-2]
        last_low = df["Low"].iloc[-1]
        last_close = df["Close"].iloc[-1]

        return last_low < prev_low and last_close > prev_low

    except Exception as e:

        logger.debug(f"Liquidity sweep error: {e}")

        return False


# =====================================================
# STOP HUNT
# =====================================================

def detect_stop_hunt(df):

    try:

        prev_high = df["High"].iloc[-2]
        last_high = df["High"].iloc[-1]
        last_close = df["Close"].iloc[-1]

        return last_high > prev_high and last_close < prev_high

    except Exception as e:

        logger.debug(f"Stop hunt error: {e}")

        return False


# =====================================================
# FAKE BREAKOUT
# =====================================================

def detect_fake_breakout(df):

    try:

        high20 = df["High"].rolling(20).max().iloc[-2]

        last_high = df["High"].iloc[-1]
        last_close = df["Close"].iloc[-1]

        return last_high > high20 and last_close < high20

    except Exception as e:

        logger.debug(f"Fake breakout error: {e}")

        return False


# =====================================================
# MOMENTUM BURST
# =====================================================

def detect_momentum_burst(df):

    try:

        avg_vol = df["Volume"].rolling(20).mean().iloc[-2]
        last_vol = df["Volume"].iloc[-1]

        if avg_vol == 0:
            return False

        return last_vol > avg_vol * 2

    except Exception as e:

        logger.debug(f"Momentum burst error: {e}")

        return False


# =====================================================
# VOLUME EXPANSION
# =====================================================

def detect_volume_expansion(df):

    try:

        avg_vol = df["Volume"].rolling(20).mean().iloc[-1]
        last_vol = df["Volume"].iloc[-1]

        if avg_vol == 0:
            return False

        return last_vol > avg_vol * 1.5

    except Exception as e:

        logger.debug(f"Volume expansion error: {e}")

        return False


# =====================================================
# MARKET RADAR ENGINE
# =====================================================

def analyze_market_radar(ticker, df):

    try:

        if not valid_df(df):
            return None

        events = []

        if detect_liquidity_sweep(df):
            events.append("Liquidity Sweep")

        if detect_stop_hunt(df):
            events.append("Stop Hunt")

        if detect_fake_breakout(df):
            events.append("Fake Breakout")

        if detect_momentum_burst(df):
            events.append("Momentum Burst")

        if detect_volume_expansion(df):
            events.append("Volume Expansion")

        if not events:
            return None

        return {

            "ticker": ticker,
            "events": events,
            "timestamp": datetime.utcnow().isoformat()

        }

    except Exception as e:

        logger.error(f"Market radar error {ticker}: {e}")

        return None


# =====================================================
# FORMAT RADAR MESSAGE
# =====================================================

def format_market_radar(radar):

    try:

        ticker = radar["ticker"]

        text = f"""
🧠 AI MARKET RADAR

Ticker: {ticker}

Events detected:
"""

        for event in radar["events"]:

            text += f"• {event}\n"

        return text.strip()

    except Exception as e:

        logger.error(f"Radar formatting error: {e}")

        return "Radar formatting error"