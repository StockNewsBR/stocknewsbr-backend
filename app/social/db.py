from __future__ import annotations

import threading

from app.core.settings import is_production_environment
from app.database import Base, engine
from app.database_schema import validate_required_tables
from app.models import SocialComment, SocialFollow, SocialLike, SocialPost, SocialRepost, SocialSentimentVote

_lock = threading.Lock()
_initialized = False
SOCIAL_REQUIRED_TABLES = (
    "social_posts",
    "social_comments",
    "social_likes",
    "social_reposts",
    "social_follows",
    "social_sentiment_votes",
)


def ensure_social_tables():
    global _initialized

    if _initialized:
        return

    with _lock:
        if _initialized:
            return

        if is_production_environment():
            validate_required_tables(engine, SOCIAL_REQUIRED_TABLES)
            _initialized = True
            return

        Base.metadata.create_all(
            bind=engine,
            tables=[
                SocialPost.__table__,
                SocialComment.__table__,
                SocialLike.__table__,
                SocialRepost.__table__,
                SocialFollow.__table__,
                SocialSentimentVote.__table__,
            ],
        )
        _initialized = True
