"""Regression test for the S1 threadpool-offload concurrency fallout.

Before S1, `like_post` / `create_repost` ran synchronously inline inside an
`async def` handler with no `await` in the middle of their check-then-insert
sequence — that made the read-check-insert-commit effectively atomic within a
process even without an explicit lock. S1 moved these calls into
`run_in_threadpool`, so they now run on genuinely parallel OS threads: two
requests can both read "no existing like/repost" before either commits, and
the loser's `db.commit()` raises `IntegrityError` against
`uq_social_like_post_user` / `uq_social_repost_post_user`.

These tests force that exact TOCTOU window deterministically (seed the
"winning" row as if another thread already committed it, then make the
function's own read miss it) and assert the real `IntegrityError` raised by
the unique constraint is caught, rolled back, and resolved to the existing
row instead of propagating as an unhandled 500.

Isolation mirrors tests/test_s1_async_db_offload.py (in-memory StaticPool
engine + SessionLocal patches on the social modules + moderation state in a
tempdir) so no row reaches stocknews.db.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Query, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import SocialLike, SocialRepost
from app.social import db as social_db
from app.social import likes as social_likes
from app.social import moderation
from app.social import posts as social_posts
from app.social import reposts as social_reposts


class _RaceRegressionBase(unittest.TestCase):
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

        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        original_moderation_path = moderation.MODERATION_STORE_PATH
        moderation.MODERATION_STORE_PATH = Path(self.tempdir.name) / "moderation_state.json"
        self.addCleanup(setattr, moderation, "MODERATION_STORE_PATH", original_moderation_path)

        self._patched = []
        for module in (social_posts, social_likes, social_reposts):
            self._patched.append((module, module.SessionLocal))
            module.SessionLocal = self.SessionLocal
        original_initialized = social_db._initialized
        social_db._initialized = True

        def _restore():
            for module, original in self._patched:
                module.SessionLocal = original
            social_db._initialized = original_initialized
            Base.metadata.drop_all(bind=self.engine)
            self.engine.dispose()

        self.addCleanup(_restore)

        db = self.SessionLocal()
        post = social_posts.create_post(
            user_id=1,
            text="Fluxo comprador seguindo forte no book.",
            ticker="PETR4",
            display_name="Trader",
            email="trader@example.com",
        )
        db.close()
        self.post_id = post["id"]

    def _miss_next_query_once(self):
        """Patch Query.first so the *next* call returns None, then behaves normally.

        Simulates the function's own read landing in the TOCTOU window, before
        the concurrently-committed row (seeded below) is visible to it.
        """
        real_first = Query.first
        state = {"armed": True}

        def flaky_first(query_self):
            if state["armed"]:
                state["armed"] = False
                return None
            return real_first(query_self)

        return patch.object(Query, "first", flaky_first)


class LikePostRaceTests(_RaceRegressionBase):
    def test_concurrent_like_insert_race_does_not_raise_and_keeps_single_row(self):
        seed_db = self.SessionLocal()
        seed_db.add(SocialLike(post_id=self.post_id, user_id=7))
        seed_db.commit()
        seed_db.close()

        with self._miss_next_query_once():
            count = social_likes.like_post(self.post_id, 7)

        self.assertEqual(count, 1, "the race must not create a duplicate like row")

        verify_db = self.SessionLocal()
        rows = (
            verify_db.query(SocialLike)
            .filter(SocialLike.post_id == self.post_id, SocialLike.user_id == 7)
            .all()
        )
        verify_db.close()
        self.assertEqual(len(rows), 1)


class CreateRepostRaceTests(_RaceRegressionBase):
    def test_concurrent_repost_insert_race_does_not_raise_and_resolves_to_existing_row(self):
        seed_db = self.SessionLocal()
        winner = SocialRepost(post_id=self.post_id, user_id=7, quote_text="chegou primeiro")
        seed_db.add(winner)
        seed_db.commit()
        seed_db.refresh(winner)
        winner_id = winner.id
        seed_db.close()

        with self._miss_next_query_once():
            result = social_reposts.create_repost(self.post_id, 7, quote_text="perdeu a corrida")

        self.assertIsNotNone(result)
        self.assertNotIn("error", result)
        self.assertEqual(result["id"], winner_id, "must resolve to the row that actually won the insert race")
        self.assertEqual(result["quote_text"], "chegou primeiro")

        verify_db = self.SessionLocal()
        rows = (
            verify_db.query(SocialRepost)
            .filter(SocialRepost.post_id == self.post_id, SocialRepost.user_id == 7)
            .all()
        )
        verify_db.close()
        self.assertEqual(len(rows), 1, "the race must not create a duplicate repost row")


if __name__ == "__main__":
    unittest.main()
