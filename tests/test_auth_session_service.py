import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User, UserSession
from app.security import hash_password
from app.services.auth_session_service import (
    consume_login_challenge,
    consume_telegram_link_token,
    create_telegram_link_token,
    create_user_session,
    login_requires_email_otp,
    start_login_challenge,
)


class AuthSessionServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False)
        self.db = self.SessionLocal()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _user(self, email: str, plan: str = "trial"):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        user = User(
            email=email,
            password_hash=hash_password("123456"),
            display_name="Teste",
            is_active=True,
            is_verified=True,
            plan=plan,
            plan_status="active" if plan != "trial" else "trialing",
            access_app=True,
            access_web=True,
            access_telegram=True,
            referral_code=f"SNB{email.split('@')[0].upper()}",
            created_at=now,
            updated_at=now,
            trial_expires_at=now + timedelta(days=30),
            plan_expires_at=now + timedelta(days=30) if plan == "premium" else None,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def test_premium_requires_otp(self):
        premium_user = self._user("premium@example.com", plan="premium")
        trial_user = self._user("trial@example.com", plan="trial")

        self.assertTrue(login_requires_email_otp(premium_user))
        self.assertFalse(login_requires_email_otp(trial_user))

    def test_premium_session_revokes_previous_same_channel(self):
        user = self._user("session@example.com", plan="premium")

        first = create_user_session(self.db, user, channel="web", device_id="a", device_label="chrome")
        self.db.commit()
        second = create_user_session(self.db, user, channel="web", device_id="b", device_label="edge")
        self.db.commit()

        sessions = self.db.query(UserSession).filter(UserSession.user_id == user.id).all()
        revoked = [item for item in sessions if item.revoked_at is not None]
        active = [item for item in sessions if item.revoked_at is None]

        self.assertEqual(first.channel, "web")
        self.assertEqual(len(revoked), 1)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].session_id, second.session_id)

    def test_login_challenge_can_be_consumed(self):
        user = self._user("otp@example.com", plan="premium")
        challenge, code = start_login_challenge(self.db, user, channel="app", device_id="device-1", device_label="android")
        self.db.commit()

        resolved_user, channel, device_id, device_label, _expires_at = consume_login_challenge(
            self.db,
            login_token=challenge.login_token,
            code=code,
        )
        self.db.commit()

        self.assertEqual(resolved_user.id, user.id)
        self.assertEqual(channel, "app")
        self.assertEqual(device_id, "device-1")
        self.assertEqual(device_label, "android")

    def test_telegram_link_token_binds_account(self):
        user = self._user("telegram@example.com", plan="premium")
        token, _deep_link = create_telegram_link_token(self.db, user, origin_channel="app")
        self.db.commit()

        linked_user, consumed_token = consume_telegram_link_token(
            self.db,
            link_code=token.link_code,
            telegram_id="123456",
            telegram_username="stocktester",
        )
        self.db.commit()

        self.assertEqual(linked_user.telegram_id, "123456")
        self.assertEqual(linked_user.telegram_username, "stocktester")
        self.assertIsNotNone(consumed_token.consumed_at)


if __name__ == "__main__":
    unittest.main()
