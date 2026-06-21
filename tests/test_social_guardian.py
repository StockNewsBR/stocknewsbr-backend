import tempfile
import unittest
from pathlib import Path

from app.social import moderation
from app.social.comments import add_comment
from app.social.guardian import SocialGuardian
from app.social.posts import create_post
from app.social.reposts import create_repost
from app.services import ticker_room_service


class SocialGuardianTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_moderation_path = moderation.MODERATION_STORE_PATH
        self.original_room_path = ticker_room_service.ROOM_STORE_PATH
        moderation.MODERATION_STORE_PATH = Path(self.tempdir.name) / "moderation_state.json"
        ticker_room_service.ROOM_STORE_PATH = Path(self.tempdir.name) / "ticker_rooms.json"

    def tearDown(self):
        moderation.MODERATION_STORE_PATH = self.original_moderation_path
        ticker_room_service.ROOM_STORE_PATH = self.original_room_path
        self.tempdir.cleanup()

    def test_social_guardian_blocks_links_emails_phones_and_bets(self):
        blocked_cases = {
            "acesse www.google.com": "link_detected",
            "https://google.com": "link_detected",
            "stocknewsbr.com.br": "link_detected",
            "meusite.ai": "link_detected",
            "abc@gmail.com": "email_detected",
            "teste yahoo agora": "email_detected",
            "usuario@empresa.com": "email_detected",
            "me chama no 11 99999-9999": "phone_detected",
            "16999999999": "phone_detected",
            "+55 chama agora": "phone_detected",
            "(16) falar comigo": "phone_detected",
            "manda no WhatsApp": "phone_detected",
            "grupo no Telegram": "phone_detected",
            "aposta no tigrinho": "betting_detected",
            "bet365 e blaze": "betting_detected",
            "esportes da sorte": "betting_detected",
            "pixbet": "betting_detected",
        }

        for text, expected_reason in blocked_cases.items():
            with self.subTest(text=text):
                allowed, reason = moderation.can_publish(101, text)
                self.assertFalse(allowed)
                self.assertEqual(reason, expected_reason)

    def test_blocked_content_is_not_saved_by_social_entrypoints(self):
        self.assertEqual(create_post(999, "veja stocknewsbr.com.br").get("reason"), "link_detected")
        self.assertEqual(add_comment(1, 999, "usuario@empresa.com").get("reason"), "email_detected")
        self.assertEqual(create_repost(1, 999, "aposta na bet365").get("reason"), "betting_detected")
        self.assertEqual(
            ticker_room_service.append_room_message("PETR4", 999, "Tester", "chama no +55").get("reason"),
            "phone_detected",
        )

    def test_external_attachment_url_is_blocked_but_local_media_path_is_allowed(self):
        blocked = create_post(
            user_id=999,
            text="comentario normal",
            image_url="https://evil.example.com/fake.gif",
        )
        self.assertEqual(blocked.get("reason"), "link_detected")

        allowed, reason = moderation.validate_attachment_url(999, "/media/posts/chart.gif")
        self.assertTrue(allowed)
        self.assertEqual(reason, "allowed")

    def test_guardian_score_and_audit_track_approvals_reports_and_removals(self):
        for post_id in (10, 11, 12):
            moderation.record_content_approved(77, content_type="post", content_id=post_id, post_id=post_id, ticker="PETR4")

        score_after_approvals = moderation.get_user_guardian_score(77)
        self.assertEqual(score_after_approvals["label"], "Verde")
        self.assertGreater(score_after_approvals["score"], SocialGuardian.TRUST_START)

        moderation.report(55, 10, reason="Manipulação", target_user_id=77)
        moderation.record_post_removed(10, actor_user_id=1, target_user_id=77, reason="remove")

        score_after_reports = moderation.get_user_guardian_score(77)
        self.assertLess(score_after_reports["score"], score_after_approvals["score"])

        actions = [item["action"] for item in moderation.get_guardian_audit(limit=20)]
        self.assertIn("post_created", actions)
        self.assertIn("post_reported", actions)
        self.assertIn("user_reported", actions)
        self.assertIn("post_removed", actions)

    def test_report_reason_normalization_matches_required_reasons(self):
        self.assertEqual(SocialGuardian.normalize_report_reason("Spam"), "spam")
        self.assertEqual(SocialGuardian.normalize_report_reason("Golpe"), "golpe")
        self.assertEqual(SocialGuardian.normalize_report_reason("Manipulação"), "manipulacao")
        self.assertEqual(SocialGuardian.normalize_report_reason("Ofensivo"), "ofensivo")
        self.assertEqual(SocialGuardian.normalize_report_reason("Fake News"), "fake_news")
        self.assertEqual(SocialGuardian.normalize_report_reason("qualquer outro"), "outro")


if __name__ == "__main__":
    unittest.main()
