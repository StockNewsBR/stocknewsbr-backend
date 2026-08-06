"""Mission 34 / S2 - comment listing loads moderation state once per request.

`get_comments` and `get_comments_for_posts` used to call the singular
`get_user_guardian_score` once per comment, rereading and reparsing the
moderation state file each time (N+1 of file I/O + JSON parse). After S2 they
call the batch `get_user_guardian_scores` exactly once per request, mirroring
`app/social/posts.py`. These checks pin that: the batch helper is called once
and the singular helper is never called on the listing path, while the public
JSON keeps its guardian score/label fields.

Isolation mirrors tests/test_mission_c23_social_cross_user_isolation.py: the
global SessionLocal points at the working stocknews.db, so we bind the social
modules to a private in-memory engine and point moderation state at a tempdir,
restoring both on cleanup.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.social import comments as social_comments
from app.social import moderation
from app.social import posts as social_posts


class CommentGuardianBatchTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

        # Private engine: comment/post rows land here, never stocknews.db.
        self.engine = create_engine(
            f"sqlite:///{Path(self._tmp.name) / 'comments_batch.db'}",
            future=True,
        )
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(bind=self.engine)
        Session = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False, future=True
        )

        for module in (social_comments, social_posts):
            self._patch(patch.object(module, "SessionLocal", Session))
            self._patch(patch.object(module, "ensure_social_tables", lambda: None))

        # Moderation state file -> tempdir, not the real MODERATION_STORE_PATH.
        self._original_moderation_path = moderation.MODERATION_STORE_PATH
        moderation.MODERATION_STORE_PATH = (
            Path(self._tmp.name) / "moderation_state.json"
        )

        def _restore_moderation_path():
            moderation.MODERATION_STORE_PATH = self._original_moderation_path

        self.addCleanup(_restore_moderation_path)

    def _patch(self, patcher):
        patcher.start()
        self.addCleanup(patcher.stop)

    def _seed_post(self, user_id):
        post = social_posts.create_post(user_id=user_id, text="post base")
        self.assertTrue(post and post.get("id"))
        return int(post["id"])

    def test_get_comments_calls_guardian_scores_once_for_many_comments(self):
        post_id = self._seed_post(7001)
        for uid in (7002, 7003, 7004, 7005, 7006):
            created = social_comments.add_comment(post_id, uid, f"comentario do usuario {uid}")
            self.assertIsInstance(created, dict)
            self.assertNotIn("error", created)

        with patch.object(
            social_comments,
            "get_user_guardian_scores",
            wraps=social_comments.get_user_guardian_scores,
        ) as batch_spy, patch.object(
            social_comments,
            "get_user_guardian_score",
            wraps=social_comments.get_user_guardian_score,
        ) as single_spy:
            result = social_comments.get_comments(post_id)

        self.assertEqual(len(result), 5)
        # OLD: singular helper called once per comment (5x); NEW: batch once, singular 0x.
        self.assertEqual(batch_spy.call_count, 1)
        self.assertEqual(single_spy.call_count, 0)
        for item in result:
            self.assertIn("social_guardian_score", item)
            self.assertIn("social_guardian_label", item)
            self.assertIsNotNone(item["social_guardian_score"])

    def test_get_comments_for_posts_calls_guardian_scores_once_across_posts(self):
        post_ids = [self._seed_post(7101 + i) for i in range(3)]
        uid_pool = [7201, 7202, 7203, 7204]
        for i, post_id in enumerate(post_ids):
            for j in range(3):
                uid = uid_pool[(i + j) % len(uid_pool)]
                self.assertNotIn("error", social_comments.add_comment(post_id, uid, f"c {uid}"))

        with patch.object(
            social_comments,
            "get_user_guardian_scores",
            wraps=social_comments.get_user_guardian_scores,
        ) as batch_spy, patch.object(
            social_comments,
            "get_user_guardian_score",
            wraps=social_comments.get_user_guardian_score,
        ) as single_spy:
            grouped = social_comments.get_comments_for_posts(post_ids)

        self.assertEqual(sum(len(v) for v in grouped.values()), 9)
        self.assertEqual(batch_spy.call_count, 1)
        self.assertEqual(single_spy.call_count, 0)
        for serialized_list in grouped.values():
            for item in serialized_list:
                self.assertIn("social_guardian_score", item)
                self.assertIsNotNone(item["social_guardian_score"])


if __name__ == "__main__":
    unittest.main()
