from __future__ import annotations

import threading

from app.database import Base, engine
from app.models import SocialComment, SocialFollow, SocialLike, SocialPost, SocialRepost, SocialSentimentVote

_lock = threading.Lock()
_initialized = False


def ensure_social_tables():
    global _initialized

    if _initialized:
        return

    with _lock:
        if _initialized:
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
