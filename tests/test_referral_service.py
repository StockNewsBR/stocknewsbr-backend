import unittest
from datetime import datetime, timedelta

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base
    from app.models import Referral, ReferralStats, SubscriptionAuditLog, User
    from app.services.referrals import referral_badge, referral_leaderboard, validate_referrals

    IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    IMPORT_ERROR = exc


@unittest.skipIf(IMPORT_ERROR is not None, f"runtime dependency unavailable: {IMPORT_ERROR}")
class ReferralServiceTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine, expire_on_commit=False)
        self.db = self.Session()
        self.now = datetime(2026, 5, 14, 12, 0, 0)

    def tearDown(self):
        self.db.close()

    def _user(self, email, name, code, plan="trial"):
        user = User(
            email=email,
            password_hash="hash",
            display_name=name,
            referral_code=code,
            is_active=True,
            is_verified=True,
            plan=plan,
            plan_status="active" if plan == "premium" else "trialing",
            trial_expires_at=self.now + timedelta(days=30) if plan == "trial" else None,
            plan_expires_at=self.now + timedelta(days=30) if plan == "premium" else None,
            access_app=True,
            access_web=plan == "premium",
            access_telegram=plan == "premium",
        )
        self.db.add(user)
        self.db.flush()
        return user

    def _paid_referral(self, referrer, index, paid_days_ago=8):
        referred = self._user(
            f"paid{index}@example.com",
            f"Cliente {index}",
            f"SNBPAID{index}",
            plan="premium",
        )
        self.db.add(
            Referral(
                referrer_id=referrer.id,
                referred_user_id=referred.id,
                status="pending",
                created_at=self.now - timedelta(days=20),
            )
        )
        self.db.add(
            SubscriptionAuditLog(
                user_id=referred.id,
                provider="stripe",
                event_type="invoice.payment_succeeded",
                product_id="premium_br_monthly",
                origin="website",
                status="active",
                created_at=self.now - timedelta(days=paid_days_ago),
            )
        )
        self.db.flush()
        return referred

    def test_referral_validates_only_on_day_8_after_paid_window(self):
        referrer = self._user("joao@example.com", "Joao Silva", "SNBJOAO", plan="premium")
        self._paid_referral(referrer, 1, paid_days_ago=7)
        self.db.commit()

        result = validate_referrals(self.db, now=self.now)

        self.assertEqual(result["validated"], 0)
        referral = self.db.query(Referral).first()
        self.assertEqual(referral.status, "pending")

    def test_three_paid_referrals_grant_one_month_and_leaderboard_masks_names(self):
        referrer = self._user("joao@example.com", "Joao Silva", "SNBJOAO", plan="premium")
        initial_expiry = referrer.plan_expires_at
        for index in range(1, 4):
            self._paid_referral(referrer, index, paid_days_ago=8)
        self.db.commit()

        result = validate_referrals(self.db, now=self.now)

        self.assertEqual(result["validated"], 3)
        stats = self.db.query(ReferralStats).filter(ReferralStats.user_id == referrer.id).first()
        self.assertEqual(stats.total_validated, 3)
        self.assertEqual(stats.reward_balance_months, 1)
        self.assertGreater(referrer.plan_expires_at, initial_expiry)

        leaderboard = referral_leaderboard(self.db)
        self.assertEqual(leaderboard["items"][0]["name"], "Joao S.")
        self.assertEqual(leaderboard["items"][0]["total_validated"], 3)
        self.assertIn("Cliente 1.", leaderboard["items"][0]["paid_referrals"])

    def test_badges_follow_requested_thresholds(self):
        self.assertIsNone(referral_badge(9))
        self.assertEqual(referral_badge(10), "Badge Vip")
        self.assertEqual(referral_badge(100), "Leaderboard VIP")


if __name__ == "__main__":
    unittest.main()
