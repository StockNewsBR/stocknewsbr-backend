# =====================================================
# SIGNAL ENGINE V2
# Ultra Fast + Crash Safe
# =====================================================

import logging

from app.ai.vector_signal_engine import (
    momentum,
    volatility,
    trend_strength
)

from app.ai.volume_explosion import detect_volume_explosion
from app.ai.smart_money_detector import detect_smart_money
from app.ai.liquidity_trap import detect_liquidity_trap
from app.ai.fake_breakout import detect_fake_breakout

logger = logging.getLogger("stocknewsbr.signal_engine")


def calculate_signal(ticker, df):

    try:

        if df is None or len(df) < 30:
            return None

        close = df["Close"].values
        volume = df["Volume"].values if "Volume" in df else None

        signals = []

        # =================================================
        # EVENT DETECTION FIRST (CHEAP)
        # =================================================

        volume_spike = detect_volume_explosion(df)

        smart_money = detect_smart_money(df)

        liquidity = detect_liquidity_trap(df)

        fake = detect_fake_breakout(df)

        if volume_spike:
            signals.append("volume_explosion")

        if smart_money:
            signals.append("smart_money")

        if liquidity:
            signals.append("liquidity_sweep")

        if fake:
            signals.append("fake_breakout")

        # =================================================
        # VECTOR INDICATORS (ONLY IF NEEDED)
        # =================================================

        momentum_val = momentum(close)
        volatility_val = volatility(close)
        trend_val = trend_strength(close)

        return {

            "signals": signals,

            "momentum": momentum_val,

            "volatility": volatility_val,

            "trend_strength": trend_val,

            "volume_spike": volume_spike,

            "liquidity_sweep": liquidity,

            "smart_money": smart_money

        }

    except Exception as e:

        logger.debug(f"Signal error {ticker}: {e}")

        return None