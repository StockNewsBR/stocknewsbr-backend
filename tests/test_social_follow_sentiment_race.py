"""The check-then-insert race, in the two places the first pass missed.

Commit 07f1316a fixed this TOCTOU in `like_post` / `create_repost`, but the
same read-check-insert-commit shape survived in two more social writers:

    app/social/followers.py::follow     -> uq_social_follow_user_target
    app/social/sentiment_poll.py::vote  -> uq_social_sentiment_vote_ticker_user

Both are reached from plain `def` routes (`POST /social/users/{id}/follow`,
`POST /sentiment/vote`). FastAPI runs sync handlers in its threadpool, so these
two never needed the S1 offload to become genuinely parallel — the window has
been open the whole time. Two requests can both read "no existing row" before
either commits, and the loser's `db.commit()` raises `IntegrityError` against
the unique constraint and surfaces as a 500.

Race forcing and isolation mirror tests/test_social_like_repost_race.py: seed
the winning row as if another thread already committed it, make the function's
own read miss it once, and assert the constraint error is caught, rolled back
and resolved — never propagated.
"""

import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Query, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import SocialFollow, SocialSentimentVote
from app.social import db as social_db
from app.social import followers as social_followers
from app.social import sentiment_poll as social_sentiment


class _RaceRegressionBase(unittest.TestCase):
    modules = ()

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(
            bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False
        )

        patched = []
        for module in self.modules:
            patched.append((module, module.SessionLocal))
            module.SessionLocal = self.SessionLocal
        original_initialized = social_db._initialized
        social_db._initialized = True

        def _restore():
            for module, original in patched:
                module.SessionLocal = original
            social_db._initialized = original_initialized
            Base.metadata.drop_all(bind=self.engine)
            self.engine.dispose()

        self.addCleanup(_restore)

    def _miss_next_query_once(self):
        """Make the *next* Query.first() return None, then behave normally.

        Simulates the function's own read landing inside the TOCTOU window,
        before the concurrently-committed row becomes visible to it.
        """
        real_first = Query.first
        state = {"armed": True}

        def flaky_first(query_self):
            if state["armed"]:
                state["armed"] = False
                return None
            return real_first(query_self)

        return patch.object(Query, "first", flaky_first)


class FollowRaceTests(_RaceRegressionBase):
    modules = (social_followers,)

    def test_concurrent_follow_race_does_not_raise_and_keeps_single_row(self):
        seed = self.SessionLocal()
        seed.add(SocialFollow(user_id=1, target_user_id=2))
        seed.commit()
        seed.close()

        with self._miss_next_query_once():
            result = social_followers.follow(1, 2)

        self.assertEqual(
            result,
            {"status": "following"},
            "losing the insert race is still a successful follow",
        )

        verify = self.SessionLocal()
        rows = (
            verify.query(SocialFollow)
            .filter(SocialFollow.user_id == 1, SocialFollow.target_user_id == 2)
            .all()
        )
        verify.close()
        self.assertEqual(len(rows), 1, "the race must not create a duplicate follow row")

    def test_uncontended_follow_still_creates_the_row(self):
        result = social_followers.follow(1, 2)

        self.assertEqual(result, {"status": "following"})

        verify = self.SessionLocal()
        rows = verify.query(SocialFollow).all()
        verify.close()
        self.assertEqual(len(rows), 1)

    def test_repeat_follow_is_idempotent(self):
        social_followers.follow(1, 2)
        result = social_followers.follow(1, 2)

        self.assertEqual(result, {"status": "following"})

        verify = self.SessionLocal()
        rows = verify.query(SocialFollow).all()
        verify.close()
        self.assertEqual(len(rows), 1)


class SentimentVoteRaceTests(_RaceRegressionBase):
    modules = (social_sentiment,)

    def test_concurrent_vote_race_does_not_raise_and_keeps_single_row(self):
        seed = self.SessionLocal()
        seed.add(SocialSentimentVote(ticker="PETR4", user_id=7, sentiment="bullish"))
        seed.commit()
        seed.close()

        with self._miss_next_query_once():
            result = social_sentiment.vote("PETR4", "bearish", user_id=7)

        self.assertIsNotNone(result, "the race must not propagate as a failure")

        verify = self.SessionLocal()
        rows = (
            verify.query(SocialSentimentVote)
            .filter(
                SocialSentimentVote.ticker == "PETR4",
                SocialSentimentVote.user_id == 7,
            )
            .all()
        )
        verify.close()
        self.assertEqual(len(rows), 1, "the race must not create a duplicate vote row")
        self.assertEqual(
            rows[0].sentiment,
            "bearish",
            "vote() is an upsert: the caller's sentiment must win after the race",
        )

    def test_uncontended_vote_records_the_sentiment(self):
        result = social_sentiment.vote("PETR4", "bullish", user_id=7)

        self.assertIsNotNone(result)

        verify = self.SessionLocal()
        rows = verify.query(SocialSentimentVote).all()
        verify.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].sentiment, "bullish")

    def test_revote_updates_in_place(self):
        social_sentiment.vote("PETR4", "bullish", user_id=7)
        social_sentiment.vote("PETR4", "extreme_bear", user_id=7)

        verify = self.SessionLocal()
        rows = verify.query(SocialSentimentVote).all()
        verify.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].sentiment, "extreme_bear")
