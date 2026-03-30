# =====================================================
# STOCKNEWSBR AI MARKET NARRATIVE
# Fast + Crash Safe
# =====================================================

import logging

logger = logging.getLogger("stocknewsbr.market_narrative")


_SENTIMENT_LEVELS = (
    (85, "an extremely strong bullish structure"),
    (70, "strong bullish momentum"),
    (55, "moderate bullish pressure"),
    (40, "neutral market conditions"),
    (0, "a weak technical structure"),
)

_CONFLUENCE_LEVELS = (
    (7, "very high AI model agreement"),
    (5, "high AI model agreement"),
    (3, "moderate AI agreement"),
    (0, "low model agreement"),
)


def _resolve_level(value, table):

    for threshold, text in table:

        if value >= threshold:
            return text

    return table[-1][1]


def generate_market_narrative(symbol, score, confluence):

    try:

        if not symbol:
            symbol = "This asset"

        if not isinstance(score, (int, float)):
            score = 0

        if not isinstance(confluence, (int, float)):
            confluence = 0

        sentiment = _resolve_level(score, _SENTIMENT_LEVELS)
        agreement = _resolve_level(confluence, _CONFLUENCE_LEVELS)

        return (
            f"{symbol} currently shows {sentiment}. "
            f"The AI engine detected {agreement}. "
            f"Multiple technical indicators and liquidity signals appear aligned."
        )

    except Exception:

        logger.exception("Market narrative error")

        return "AI narrative unavailable."