import unittest
from datetime import datetime, timedelta, timezone

try:
    from app.services.access_service import (
        _default_plan_days,
        activate_subscription,
        grant_trial_access,
        pricing_catalog,
        refresh_user_access,
        trial_days_for_market,
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
        self.assertEqual(_default_plan_days("premium_annual"), 365)
        self.assertEqual(_default_plan_days("premium_anual"), 365)
        self.assertEqual(_default_plan_days("premium_mensal"), 31)

    def test_trial_policy_starts_with_30_days_and_shortens_after_launch_window(self):
        launch_day = datetime(2026, 5, 14)
        after_launch_window = datetime(2026, 6, 14)

        self.assertEqual(trial_days_for_market("BR", launch_day), 30)
        self.assertEqual(trial_days_for_market("USA", launch_day), 30)
        self.assertEqual(trial_days_for_market("BR", after_launch_window), 14)
        self.assertEqual(trial_days_for_market("USA", after_launch_window), 14)

    def test_grant_trial_access_uses_current_trial_policy(self):
        user = DummyUser()
        user.trial_expires_at = None

        grant_trial_access(user, now=datetime(2026, 5, 14))

        self.assertEqual(user.plan, "trial")
        self.assertEqual((user.trial_expires_at - datetime(2026, 5, 14)).days, 30)
        self.assertTrue(user.access_app)
        self.assertTrue(user.access_web)
        self.assertTrue(user.access_telegram)

    def test_pricing_catalog_separates_br_and_usa_and_refund_window(self):
        catalog = pricing_catalog("USA", datetime(2026, 5, 14))

        self.assertEqual(catalog["selected"]["currency"], "USD")
        self.assertEqual(catalog["plans"]["BR"]["monthly_amount"], 49)
        self.assertEqual(catalog["plans"]["BR"]["annual_amount"], 500)
        self.assertEqual(catalog["plans"]["USA"]["monthly_amount"], 49)
        self.assertEqual(catalog["plans"]["USA"]["annual_amount"], 500)
        self.assertEqual(catalog["refund_window_days"], 7)


if __name__ == "__main__":
    unittest.main()
