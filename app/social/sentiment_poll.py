# =====================================================
# SENTIMENT POLL ENGINE (SAFE)
# =====================================================

from collections import defaultdict

polls = defaultdict(lambda: {
    "extreme_bear": 0,
    "bearish": 0,
    "neutral": 0,
    "bullish": 0,
    "extreme_bull": 0
})

SENTIMENT_WEIGHTS = {
    "extreme_bear": -2,
    "bearish": -1,
    "neutral": 0,
    "bullish": 1,
    "extreme_bull": 2
}


def vote(ticker: str, sentiment: str):

    if not ticker:
        return None

    ticker = ticker.upper()
    sentiment = sentiment.lower()

    if sentiment not in SENTIMENT_WEIGHTS:
        return None

    polls[ticker][sentiment] += 1

    return get_sentiment(ticker)


def get_sentiment(ticker: str):
    ticker = ticker.upper()

    data = polls[ticker]

    total = sum(data.values())

    if total == 0:
        return {
            "ticker": ticker,
            "score": 0,
            "label": "Neutral",
            "votes": data
        }

    weighted = sum(
        data[k] * SENTIMENT_WEIGHTS[k]
        for k in data
    )

    score = round((weighted / (total * 2)) * 100)

    return {
        "ticker": ticker,
        "score": score,
        "label": sentiment_label(score),
        "votes": data
    }


def sentiment_label(score):

    if score <= -60:
        return "Extreme Bear"

    if score <= -20:
        return "Bearish"

    if score < 20:
        return "Neutral"

    if score < 60:
        return "Bullish"

    return "Extreme Bull"
