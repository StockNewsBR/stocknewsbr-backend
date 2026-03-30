# =====================================================
# GLOBAL RADAR ANALYZER
# Fast + Safe
# =====================================================

from app.ai.smart_money_detector import detect_smart_money
from app.ai.volume_explosion import detect_volume_explosion
from app.ai.trend_acceleration import detect_trend_acceleration
from app.ai.fake_breakout import detect_fake_breakout
from app.ai.liquidity_trap import detect_liquidity_trap


def analyze_radar(df):

    if df is None:
        return []

    signals = []

    try:

        if detect_volume_explosion(df):
            signals.append("volume_explosion")

        if detect_smart_money(df):
            signals.append("smart_money_entry")

        if detect_trend_acceleration(df):
            signals.append("trend_acceleration")

        if detect_fake_breakout(df):
            signals.append("fake_breakout")

        if detect_liquidity_trap(df):
            signals.append("liquidity_trap")

    except Exception:

        return []

    return signals