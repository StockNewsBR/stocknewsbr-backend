from app.social.store import mutate_social_state, read_social_state

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

    def _vote(state):
        polls = dict(state.get("sentiment_polls", {}))
        poll = dict(
            polls.get(
                ticker,
                {
                    "extreme_bear": 0,
                    "bearish": 0,
                    "neutral": 0,
                    "bullish": 0,
                    "extreme_bull": 0,
                },
            )
        )
        poll[sentiment] = int(poll.get(sentiment, 0)) + 1
        polls[ticker] = poll
        state["sentiment_polls"] = polls
        return poll

    mutate_social_state(_vote)
    return get_sentiment(ticker)


def get_sentiment(ticker: str):
    ticker = ticker.upper()

    def _read(state):
        polls = dict(state.get("sentiment_polls", {}))
        return dict(
            polls.get(
                ticker,
                {
                    "extreme_bear": 0,
                    "bearish": 0,
                    "neutral": 0,
                    "bullish": 0,
                    "extreme_bull": 0,
                },
            )
        )

    data = read_social_state(_read)

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
