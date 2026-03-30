import unittest
from datetime import datetime, timedelta, timezone

try:
    from app.services.access_service import (
        _default_plan_days,
        activate_subscription,
        refresh_user_access,
    )
    IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    IMPORT_ERROR = exc


class DummyUser:
    def __init__(self):
        self.id = 1
        self.email = "tester@example.com"
        self.display_name = "Tester"
        self.phone = None
        self.is_active = True
        self.is_verified = True
        self.plan = "trial"
        self.plan_status = "trialing"
        self.trial_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        self.plan_expires_at = None
        self.access_app = True
        self.access_web = True
        self.access_telegram = True
        self.telegram_id = None
        self.telegram_username = None
        self.subscription_provider = None
        self.subscription_origin = None
        self.subscription_product_id = None
        self.external_subscription_id = None
        self.google_play_purchase_token = None
        self.stripe_customer_id = None
        self.stripe_subscription_id = None
        self.legal_notice_version = "2026-03"
        self.accepted_terms_at = None
        self.accepted_privacy_at = None
        self.accepted_risk_notice_at = None
        self.referral_code = "SNBTEST"
        self.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.last_access_at = None


@unittest.skipIf(IMPORT_ERROR is not None, f"runtime dependency unavailable: {IMPORT_ERROR}")
class AccessServiceTests(unittest.TestCase):
    def test_trial_expiry_downgrades_to_free(self):
        user = DummyUser()

        refresh_user_access(user)

        self.assertEqual(user.plan, "free")
        self.assertTrue(user.access_app)
        self.assertFalse(user.access_web)
        self.assertFalse(user.access_telegram)

    def test_annual_product_extends_plan_for_one_year(self):
        user = DummyUser()
        user.plan = "free"
        user.trial_expires_at = None

        activate_subscription(
            user,
            provider="google_play",
            product_id="premium_annual",
            origin="android_app",
        )

        self.assertEqual(user.plan, "premium")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.assertGreaterEqual((user.plan_expires_at - now).days, 360)

    def test_default_plan_days_detects_annual_keywords(self):
        self.assertEqual(_default_plan_days("premium_annual"), 366)
        self.assertEqual(_default_plan_days("premium_anual"), 366)
        self.assertEqual(_default_plan_days("premium_mensal"), 31)


if __name__ == "__main__":
    unittest.main()
