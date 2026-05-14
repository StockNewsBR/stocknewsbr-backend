import unittest
from datetime import datetime

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.api import stripe_webhook
    from app.database import Base
    from app.models import SubscriptionAuditLog, User

    IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    IMPORT_ERROR = exc


@unittest.skipIf(IMPORT_ERROR is not None, f"runtime dependency unavailable: {IMPORT_ERROR}")
class StripeWebhookTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine, expire_on_commit=False)
        self.db = self.Session()
        self.original_session_local = stripe_webhook.SessionLocal
        stripe_webhook.SessionLocal = lambda: self.db
        app = FastAPI()
        app.include_router(stripe_webhook.router)
        self.client = TestClient(app)

    def tearDown(self):
        stripe_webhook.SessionLocal = self.original_session_local
        self.db.close()

    def test_checkout_completed_activates_access_and_logs_sandbox_event(self):
        user = User(
            email="stripe@example.com",
            password_hash="hash",
            display_name="Stripe Tester",
            referral_code="SNBSTRIPE",
            is_active=True,
            is_verified=True,
            plan="trial",
            plan_status="trialing",
            trial_expires_at=datetime(2026, 6, 14),
            access_app=True,
            access_web=True,
            access_telegram=True,
        )
        self.db.add(user)
        self.db.commit()

        response = self.client.post(
            "/billing/stripe/webhook",
            json={
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "customer": "cus_sandbox",
                        "subscription": "sub_sandbox",
                        "metadata": {
                            "user_id": str(user.id),
                            "product_id": "premium_br_monthly",
                        },
                    }
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(user.plan, "premium")
        self.assertTrue(user.access_web)
        self.assertTrue(user.access_telegram)
        self.assertEqual(user.stripe_customer_id, "cus_sandbox")
        self.assertEqual(user.stripe_subscription_id, "sub_sandbox")

        event = self.db.query(SubscriptionAuditLog).filter(SubscriptionAuditLog.user_id == user.id).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, "checkout.session.completed")
        self.assertEqual(event.status, "active")


if __name__ == "__main__":
    unittest.main()
