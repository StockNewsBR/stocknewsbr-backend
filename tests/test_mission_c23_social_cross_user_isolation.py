"""Mission C23 - social mutations must stay scoped to their owner.

Social tables carry no RLS (only media_assets and promo_redemptions do), so
ownership on posts and reposts is enforced purely in the application layer:
`delete_post` compares `post.user_id` against the caller and `delete_repost`
puts the owner in the same query. Both are reached from routes that take the
resource id from the path and the user from the session.

Nothing pinned that. These are two-user checks against a temporary SQLite
database -- the global SessionLocal points at the working `stocknews.db`, so
each test binds the social modules to its own engine.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import SocialPost, SocialRepost
from app.social import posts as social_posts
from app.social import reposts as social_reposts

USER_A = 101
USER_B = 202
MODERATOR = 303


class MissionC23SocialCrossUserIsolationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

        self.engine = create_engine(f"sqlite:///{Path(self._tmp.name) / 'social.db'}", future=True)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(bind=self.engine)
        Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

        # Ownership is what is under test, not the guardian/moderation gate.
        for module in (social_posts, social_reposts):
            self._patch(patch.object(module, "SessionLocal", Session))
            self._patch(patch.object(module, "ensure_social_tables", lambda: None))
            self._patch(patch.object(module, "can_publish", lambda *a, **k: (True, None)))
            self._patch(patch.object(module, "record_content_approved", lambda *a, **k: None))

        self._patch(patch.object(social_posts, "record_post_removed", lambda *a, **k: None))
        self._patch(patch.object(social_posts, "get_user_guardian_score", lambda *a, **k: {}))
        self._patch(patch.object(social_posts, "is_post_hidden", lambda *a, **k: False))
        self._patch(patch.object(social_posts, "validate_attachment_url", lambda *a, **k: (True, None)))

        self.Session = Session

    def _patch(self, patcher):
        patcher.start()
        self.addCleanup(patcher.stop)

    def _post_for(self, user_id):
        created = social_posts.create_post(user_id=user_id, text="analise do ativo", ticker="PETR4")
        self.assertIsNotNone(created)
        return int(created["id"])

    def _post_rows(self):
        with self.Session() as session:
            return session.query(SocialPost).count()

    def test_other_user_cannot_delete_a_post(self):
        post_id = self._post_for(USER_A)

        self.assertFalse(social_posts.delete_post(post_id, USER_B))
        self.assertEqual(self._post_rows(), 1, "B's delete must not remove A's post")

    def test_owner_can_delete_their_own_post(self):
        post_id = self._post_for(USER_A)

        self.assertTrue(social_posts.delete_post(post_id, USER_A))
        self.assertEqual(self._post_rows(), 0)

    def test_moderator_may_delete_another_users_post(self):
        post_id = self._post_for(USER_A)

        self.assertTrue(social_posts.delete_post(post_id, MODERATOR, can_moderate=True))
        self.assertEqual(self._post_rows(), 0)

    def test_non_owner_without_moderation_is_refused_even_for_missing_posts(self):
        self.assertFalse(social_posts.delete_post(999_999, USER_B))

    def test_absent_caller_identity_cannot_delete_a_post(self):
        """`user_id` defaults to None, and that default must not bypass ownership.

        The route always passes `current_user.id`, so this is not reachable today
        -- it pins the service so a future caller that forgets the acting user is
        refused instead of silently deleting somebody else's post.
        """
        post_id = self._post_for(USER_A)

        self.assertFalse(social_posts.delete_post(post_id, None))
        self.assertFalse(social_posts.delete_post(post_id))
        self.assertEqual(self._post_rows(), 1, "an absent caller identity must never delete a post")

    def test_absent_caller_identity_is_still_refused_with_moderation_off(self):
        post_id = self._post_for(USER_A)

        self.assertFalse(social_posts.delete_post(post_id, None, can_moderate=False))
        self.assertEqual(self._post_rows(), 1)

    def test_repost_removal_is_scoped_to_its_owner(self):
        post_id = self._post_for(USER_A)
        self.assertIsNotNone(social_reposts.create_repost(post_id, USER_A))
        self.assertIsNotNone(social_reposts.create_repost(post_id, USER_B))

        self.assertTrue(social_reposts.delete_repost(post_id, USER_B))

        with self.Session() as session:
            remaining = session.query(SocialRepost).all()

        self.assertEqual([row.user_id for row in remaining], [USER_A], "only B's repost may be removed")

    def test_repost_removal_by_a_stranger_changes_nothing(self):
        post_id = self._post_for(USER_A)
        self.assertIsNotNone(social_reposts.create_repost(post_id, USER_A))

        self.assertFalse(social_reposts.delete_repost(post_id, USER_B))

        with self.Session() as session:
            self.assertEqual(session.query(SocialRepost).count(), 1)


if __name__ == "__main__":
    unittest.main()
