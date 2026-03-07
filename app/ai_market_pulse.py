# =========================================================
# AI MARKET PULSE
# Calculates overall market sentiment
# =========================================================

def market_pulse(signals):

    if not signals:
        return {"sentiment": "neutral"}

    bullish = signals.count("bullish")
    bearish = signals.count("bearish")

    total = len(signals)

    bull_ratio = bullish / total
    bear_ratio = bearish / total

    if bull_ratio > 0.65:
        sentiment = "strong bullish"
    elif bull_ratio > 0.55:
        sentiment = "bullish"
    elif bear_ratio > 0.65:
        sentiment = "strong bearish"
    elif bear_ratio > 0.55:
        sentiment = "bearish"
    else:
        sentiment = "neutral"

    return {
        "sentiment": sentiment,
        "bullish_signals": bullish,
        "bearish_signals": bearish,
        "total_signals": total
    }