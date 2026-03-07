# =========================================================
# AI MARKET NARRATIVE
# Generates human-readable explanation for the signal
# =========================================================

def generate_market_narrative(symbol, score, confluence):

    if score >= 85:
        sentiment = "extremely strong bullish structure"
    elif score >= 70:
        sentiment = "strong bullish momentum"
    elif score >= 55:
        sentiment = "moderate bullish pressure"
    elif score >= 40:
        sentiment = "neutral market conditions"
    else:
        sentiment = "weak technical structure"

    if confluence >= 7:
        agreement = "very high AI model agreement"
    elif confluence >= 5:
        agreement = "high AI model agreement"
    elif confluence >= 3:
        agreement = "moderate AI agreement"
    else:
        agreement = "low model agreement"

    narrative = (
        f"{symbol} currently shows {sentiment}. "
        f"The AI engine detected {agreement}. "
        f"Multiple technical indicators and liquidity signals are aligned "
        f"with the current setup."
    )

    return narrative