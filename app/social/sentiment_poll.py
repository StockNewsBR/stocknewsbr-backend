from __future__ import annotations

from app.database import SessionLocal
from app.models import SocialSentimentVote
from app.social.db import ensure_social_tables

SENTIMENT_WEIGHTS = {
    "extreme_bear": -2,
    "bearish": -1,
    "neutral": 0,
    "bullish": 1,
    "extreme_bull": 2,
}


def vote(ticker: str, sentiment: str, user_id: int | None = None):
    ensure_social_tables()
    if not ticker:
        return None

    ticker = ticker.upper().strip()
    sentiment = str(sentiment or "").lower().strip()

    if sentiment not in SENTIMENT_WEIGHTS:
        return None

    resolved_user_id = int(user_id or 0)
    if resolved_user_id <= 0:
        return None

    db = SessionLocal()

    try:
        row = (
            db.query(SocialSentimentVote)
            .filter(
                SocialSentimentVote.ticker == ticker,
                SocialSentimentVote.user_id == resolved_user_id,
            )
            .first()
        )

        if row:
            row.sentiment = sentiment
        else:
            row = SocialSentimentVote(
                ticker=ticker,
                user_id=resolved_user_id,
                sentiment=sentiment,
            )
            db.add(row)

        db.commit()
    finally:
        db.close()

    return get_sentiment(ticker)


def get_sentiment(ticker: str):
    ensure_social_tables()
    ticker = ticker.upper().strip()
    db = SessionLocal()

    try:
        rows = (
            db.query(SocialSentimentVote.sentiment)
            .filter(SocialSentimentVote.ticker == ticker)
            .all()
        )
    finally:
        db.close()

    data = {
        "extreme_bear": 0,
        "bearish": 0,
        "neutral": 0,
        "bullish": 0,
        "extreme_bull": 0,
    }

    for row in rows:
        sentiment = row[0]
        if sentiment in data:
            data[sentiment] += 1

    total = sum(data.values())

    if total == 0:
        return {
            "ticker": ticker,
            "score": 0,
            "label": "Neutral",
            "votes": data,
        }

    weighted = sum(data[key] * SENTIMENT_WEIGHTS[key] for key in data)
    score = round((weighted / (total * 2)) * 100)

    return {
        "ticker": ticker,
        "score": score,
        "label": sentiment_label(score),
        "votes": data,
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
