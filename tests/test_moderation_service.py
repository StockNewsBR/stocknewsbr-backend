import tempfile
import unittest
from pathlib import Path

from app.social import moderation


class ModerationServiceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_path = moderation.MODERATION_STORE_PATH
        moderation.MODERATION_STORE_PATH = Path(self.tempdir.name) / "moderation_state.json"

    def tearDown(self):
        moderation.MODERATION_STORE_PATH = self.original_path
        self.tempdir.cleanup()

    def test_report_auto_hides_post_after_threshold(self):
        for user_id in range(1, moderation.REPORT_THRESHOLD_AUTO_HIDE + 1):
            moderation.report(user_id, 55, reason="spam")

        self.assertTrue(moderation.is_post_hidden(55))
        summary = moderation.get_moderation_summary()
        self.assertGreaterEqual(summary["auto_hidden_posts"], 1)

    def test_can_publish_blocks_known_phrase(self):
        allowed, reason = moderation.can_publish(22, "isso parece scam total")

        self.assertFalse(allowed)
        self.assertEqual(reason, "blocked_phrase_detected")


if __name__ == "__main__":
    unittest.main()
