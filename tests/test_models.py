import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User, PromoCode, PromoRedemption


class TestModels(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.session = SessionLocal()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def test_user_creation_and_defaults(self):
        user = User(email="test@example.com", password_hash="hash", referral_code="REF123")
        self.session.add(user)
        self.session.commit()

        self.assertIsNotNone(user.id)
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.password_hash, "hash")
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_verified)
        self.assertEqual(user.plan, "trial")
        self.assertEqual(user.plan_status, "trialing")
        self.assertTrue(user.access_app)
        self.assertTrue(user.access_web)
        self.assertTrue(user.access_telegram)
        self.assertEqual(user.legal_notice_version, "2026-03")
        self.assertEqual(user.referral_code, "REF123")
        self.assertIsInstance(user.created_at, datetime)
        self.assertIsInstance(user.updated_at, datetime)

    def test_promo_code_and_redemption(self):
        user = User(email="promo@example.com", password_hash="hash", referral_code="REF456")
        self.session.add(user)
        self.session.commit()

        promo = PromoCode(code="DISCOUNT20", free_year=False, free_months=2, max_uses=10)
        self.session.add(promo)
        self.session.commit()

        self.assertEqual(promo.current_uses, 0)
        self.assertFalse(promo.free_year)

        redemption = PromoRedemption(promo_code_id=promo.id, user_id=user.id)
        self.session.add(redemption)
        self.session.commit()

        self.assertEqual(redemption.promo_code_id, promo.id)
        self.assertEqual(redemption.user_id, user.id)
        self.assertIsInstance(redemption.redeemed_at, datetime)

    def test_unique_constraints(self):
        user1 = User(email="unique@example.com", password_hash="hash", referral_code="REF789")
        self.session.add(user1)
        self.session.commit()

        user2 = User(email="unique@example.com", password_hash="hash", referral_code="REF999")
        self.session.add(user2)

        with self.assertRaises(Exception):
            self.session.commit()

        self.session.rollback()

        user3 = User(email="different@example.com", password_hash="hash", referral_code="REF789")
        self.session.add(user3)

        with self.assertRaises(Exception):
            self.session.commit()

if __name__ == "__main__":
    unittest.main()
