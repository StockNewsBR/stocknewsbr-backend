import asyncio
import os
import tempfile
import unittest
from copy import deepcopy
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, text
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
        self.original_stripe = stripe_webhook._STRIPE
        stripe_webhook.SessionLocal = lambda: self.db
        app = FastAPI()
        app.include_router(stripe_webhook.router)
        self.client = TestClient(app)

    def tearDown(self):
        stripe_webhook.SessionLocal = self.original_session_local
        stripe_webhook._STRIPE = self.original_stripe
        self.db.close()

    def _install_stripe_event(self, event=None, error=None):
        def construct_event(payload, signature, secret):
            self.assertEqual(secret, "whsec_test_31d")
            self.assertEqual(signature, "t=123,v1=valid")
            if error:
                raise error
            return deepcopy(event)

        stripe_webhook._STRIPE = SimpleNamespace(
            Webhook=SimpleNamespace(construct_event=construct_event)
        )

    def _install_stripe_event_with_subscription(self, event=None, subscription=None, error=None):
        self.subscription_retrieve_calls = []

        def construct_event(payload, signature, secret):
            self.assertEqual(secret, "whsec_test_31d")
            self.assertEqual(signature, "t=123,v1=valid")
            if error:
                raise error
            return deepcopy(event)

        def retrieve(subscription_id):
            self.subscription_retrieve_calls.append(subscription_id)
            return subscription

        stripe_webhook._STRIPE = SimpleNamespace(
            Webhook=SimpleNamespace(construct_event=construct_event),
            Subscription=SimpleNamespace(retrieve=retrieve),
        )

    class _StripeLikeEvent:
        def __init__(self, payload):
            self.payload = payload

        def get(self, key, default=None):
            return self.payload.get(key, default)

    @contextmanager
    def _stripe_env(self, configured=True):
        previous = os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
        if configured:
            os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_31d"
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
            else:
                os.environ["STRIPE_WEBHOOK_SECRET"] = previous

    def _checkout_event(self, user, event_id="evt_checkout_31d", metadata=None, **overrides):
        metadata = dict(metadata or {})
        metadata.setdefault("user_id", str(user.id))
        metadata.setdefault("product_id", "premium_br_monthly")
        stripe_object = {
            "mode": "subscription",
            "payment_status": "paid",
            "status": "complete",
            "customer": "cus_sandbox",
            "subscription": {"id": "sub_sandbox", "status": "active"},
            "product": {"id": "premium_br_monthly"},
            "customer_email": "stripe@example.com",
            "phone": "+5511999999999",
            "card_last4": "4242",
            "metadata": metadata,
        }
        stripe_object.update(overrides)
        return {
            "id": event_id,
            "livemode": False,
            "type": "checkout.session.completed",
            "data": {
                "object": stripe_object
            },
        }

    def _invoice_event(self, user, event_id="evt_invoice_31d", metadata=None, **overrides):
        metadata = dict(metadata or {})
        metadata.setdefault("user_id", str(user.id))
        metadata.setdefault("product_id", "premium_br_monthly")
        stripe_object = {
            "paid": True,
            "status": "paid",
            "customer": "cus_sandbox",
            "subscription": {"id": "sub_sandbox", "status": "active"},
            "metadata": metadata,
            "lines": {
                "data": [
                    {
                        "price": {
                            "id": "premium_br_monthly",
                            "product": "premium_br_monthly",
                            "lookup_key": "premium_br_monthly",
                        }
                    }
                ]
            },
        }
        stripe_object.update(overrides)
        return {
            "id": event_id,
            "livemode": False,
            "type": "invoice.payment_succeeded",
            "data": {"object": stripe_object},
        }

    def _create_user(self, suffix=""):
        suffix_value = str(suffix or "")
        email_prefix = f"stripe{suffix_value}" if suffix_value else "stripe"
        normalized_suffix = suffix_value.upper().replace("-", "").replace("_", "")
        code_suffix = f"{normalized_suffix[:8]}{len(normalized_suffix):04d}" if normalized_suffix else "STRIPE"
        user = User(
            email=f"{email_prefix}@example.com",
            password_hash="hash",
            display_name="Stripe Tester",
            referral_code=f"SNB{code_suffix}",
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
        return user

    def test_checkout_completed_activates_access_and_logs_sandbox_event(self):
        user = self._create_user()
        self._install_stripe_event(self._checkout_event(user))

        with self._stripe_env():
            response = self.client.post(
                "/billing/stripe/webhook",
                content=b'{"ignored":"payload"}',
                headers={"stripe-signature": "t=123,v1=valid"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(user.plan, "premium")
        self.assertTrue(user.access_web)
        self.assertTrue(user.access_telegram)
        self.assertEqual(user.stripe_customer_id, "cus_sandbox")
        self.assertEqual(user.stripe_subscription_id, "sub_sandbox")

        event = self.db.query(SubscriptionAuditLog).filter(SubscriptionAuditLog.user_id == user.id).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.provider_event_id, "evt_checkout_31d")
        self.assertEqual(event.event_type, "checkout.session.completed")
        self.assertEqual(event.status, "active")
        self.assertEqual(
            event.payload_excerpt,
            '{"event_id":"evt_checkout_31d","event_type":"checkout.session.completed","provider":"stripe"}',
        )
        self.assertNotIn("stripe@example.com", event.payload_excerpt)
        self.assertNotIn("+5511999999999", event.payload_excerpt)
        self.assertNotIn("4242", event.payload_excerpt)

    def test_invoice_payment_succeeded_requires_paid_invoice_and_allowed_product(self):
        user = self._create_user()
        self._install_stripe_event(self._invoice_event(user))

        with self._stripe_env():
            response = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=123,v1=valid"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(user.plan, "premium")
        self.assertEqual(user.stripe_customer_id, "cus_sandbox")
        event = self.db.query(SubscriptionAuditLog).filter(SubscriptionAuditLog.user_id == user.id).first()
        self.assertEqual(event.event_type, "invoice.payment_succeeded")
        self.assertEqual(event.product_id, "premium_br_monthly")

    def test_signed_stripe_event_object_is_accepted(self):
        user = self._create_user()
        self._install_stripe_event(self._StripeLikeEvent(self._checkout_event(user, event_id="evt_object_31d")))

        with self._stripe_env():
            response = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=123,v1=valid"},
            )

        self.assertEqual(response.status_code, 200)
        event = self.db.query(SubscriptionAuditLog).filter(SubscriptionAuditLog.user_id == user.id).one()
        self.assertEqual(event.provider_event_id, "evt_object_31d")

    def test_price_id_without_product_id_does_not_activate_subscription(self):
        user = self._create_user("price-only")
        user_id = user.id
        previous_price_ids = os.environ.get("STRIPE_ALLOWED_PRICE_IDS")
        os.environ["STRIPE_ALLOWED_PRICE_IDS"] = "price_only_31d"
        self.addCleanup(
            lambda: (
                os.environ.pop("STRIPE_ALLOWED_PRICE_IDS", None)
                if previous_price_ids is None
                else os.environ.__setitem__("STRIPE_ALLOWED_PRICE_IDS", previous_price_ids)
            )
        )
        event = {
            "id": "evt_price_only_31d",
            "livemode": False,
            "type": "invoice.payment_succeeded",
            "data": {
                "object": {
                    "paid": True,
                    "status": "paid",
                    "customer": "cus_sandbox",
                    "subscription": {"id": "sub_sandbox", "status": "active"},
                    "metadata": {"user_id": str(user.id), "price_id": "price_only_31d"},
                    "lines": {"data": [{"price": {"id": "price_only_31d"}}]},
                }
            },
        }
        self._install_stripe_event(event)

        with self._stripe_env():
            response = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=123,v1=valid"},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "stripe_product_not_allowed")
        refreshed = self.db.query(User).filter(User.id == user_id).one()
        self.assertEqual(refreshed.plan, "trial")
        self.assertEqual(self.db.query(SubscriptionAuditLog).count(), 0)

    def test_metadata_product_id_cannot_override_conflicting_stripe_product(self):
        user = self._create_user("product-conflict")
        user_id = user.id
        event = self._checkout_event(
            user,
            event_id="evt_product_conflict_31d",
            product={"id": "unapproved_stripe_product"},
            metadata={"user_id": str(user.id), "product_id": "premium_br_monthly"},
        )
        self._install_stripe_event(event)

        with self._stripe_env():
            response = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=123,v1=valid"},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "stripe_product_not_allowed")
        refreshed = self.db.query(User).filter(User.id == user_id).one()
        self.assertEqual(refreshed.plan, "trial")
        self.assertEqual(self.db.query(SubscriptionAuditLog).count(), 0)

    def test_metadata_product_id_alone_does_not_authorize_activation(self):
        user = self._create_user("metadata-only-product")
        user_id = user.id
        event = self._checkout_event(
            user,
            event_id="evt_metadata_only_product_31d",
            product=None,
            metadata={"user_id": str(user.id), "product_id": "premium_br_monthly"},
        )
        self._install_stripe_event(event)

        with self._stripe_env():
            response = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=123,v1=valid"},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "stripe_product_not_allowed")
        refreshed = self.db.query(User).filter(User.id == user_id).one()
        self.assertEqual(refreshed.plan, "trial")
        self.assertEqual(self.db.query(SubscriptionAuditLog).count(), 0)

    def test_trialing_checkout_allows_no_payment_required(self):
        user = self._create_user("trial-checkout")
        event = self._checkout_event(
            user,
            event_id="evt_trialing_checkout_31d",
            payment_status="no_payment_required",
            subscription={"id": "sub_trial_31d", "status": "trialing"},
        )
        self._install_stripe_event(event)

        with self._stripe_env():
            response = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=123,v1=valid"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(user.plan, "premium")
        self.assertEqual(user.stripe_subscription_id, "sub_trial_31d")

    def test_stripe_activation_events_fail_closed_for_invalid_financial_state(self):
        cases = (
            (
                "checkout_unpaid",
                lambda user: self._checkout_event(
                    user,
                    event_id="evt_checkout_unpaid_31d",
                    payment_status="unpaid",
                ),
                "stripe_checkout_payment_not_paid",
            ),
            (
                "checkout_wrong_mode",
                lambda user: self._checkout_event(
                    user,
                    event_id="evt_checkout_mode_31d",
                    mode="payment",
                ),
                "stripe_checkout_mode_invalid",
            ),
            (
                "invoice_unpaid",
                lambda user: self._invoice_event(
                    user,
                    event_id="evt_invoice_unpaid_31d",
                    paid=False,
                ),
                "stripe_invoice_not_paid",
            ),
            (
                "subscription_missing",
                lambda user: self._checkout_event(
                    user,
                    event_id="evt_subscription_missing_31d",
                    subscription=None,
                ),
                "stripe_subscription_missing",
            ),
            (
                "customer_missing",
                lambda user: self._checkout_event(
                    user,
                    event_id="evt_customer_missing_31d",
                    customer=None,
                ),
                "stripe_customer_missing",
            ),
            (
                "subscription_status_missing",
                lambda user: self._checkout_event(
                    user,
                    event_id="evt_subscription_status_missing_31d",
                    subscription={"id": "sub_sandbox"},
                ),
                "stripe_subscription_status_missing",
            ),
            (
                "wrong_product",
                lambda user: self._checkout_event(
                    user,
                    event_id="evt_wrong_product_31d",
                    metadata={"user_id": str(user.id), "product_id": "unapproved_plan"},
                    product={"id": "unapproved_plan"},
                ),
                "stripe_product_not_allowed",
            ),
            (
                "inactive_subscription",
                lambda user: self._checkout_event(
                    user,
                    event_id="evt_inactive_subscription_31d",
                    subscription={"id": "sub_sandbox", "status": "canceled"},
                ),
                "stripe_subscription_not_active",
            ),
        )

        for label, event_factory, detail in cases:
            with self.subTest(label=label):
                user = self._create_user(label)
                user_id = user.id
                self._install_stripe_event(event_factory(user))

                with self._stripe_env():
                    response = self.client.post(
                        "/billing/stripe/webhook",
                        content=b"{}",
                        headers={"stripe-signature": "t=123,v1=valid"},
                    )

                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"], detail)
                refreshed_user = self.db.query(User).filter(User.id == user_id).one()
                self.assertEqual(refreshed_user.plan, "trial")
                self.assertEqual(refreshed_user.plan_status, "trialing")
                self.assertIsNone(refreshed_user.stripe_customer_id)
                self.assertIsNone(refreshed_user.stripe_subscription_id)
                self.assertEqual(self.db.query(SubscriptionAuditLog).count(), 0)
                self.db.rollback()

    def test_stripe_activation_with_subscription_id_fetches_status_server_side(self):
        user = self._create_user("subscription-fetch")
        event = self._checkout_event(
            user,
            event_id="evt_subscription_fetch_31d",
            subscription="sub_fetch_31d",
        )
        self._install_stripe_event_with_subscription(event, {"id": "sub_fetch_31d", "status": "active"})

        with self._stripe_env():
            response = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=123,v1=valid"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(user.plan, "premium")
        self.assertEqual(user.stripe_subscription_id, "sub_fetch_31d")
        self.assertEqual(self.subscription_retrieve_calls, ["sub_fetch_31d"])

    def test_stripe_activation_with_subscription_id_fails_closed_without_verifier(self):
        user = self._create_user("subscription-no-verifier")
        user_id = user.id
        event = self._checkout_event(
            user,
            event_id="evt_subscription_no_verifier_31d",
            subscription="sub_no_verifier_31d",
        )
        self._install_stripe_event(event)

        with self._stripe_env():
            response = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=123,v1=valid"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "stripe_subscription_verification_unavailable")
        refreshed = self.db.query(User).filter(User.id == user_id).one()
        self.assertEqual(refreshed.plan, "trial")
        self.assertEqual(self.db.query(SubscriptionAuditLog).count(), 0)

    def test_stripe_livemode_mismatch_fails_closed_without_audit_or_activation(self):
        user = self._create_user()
        user_id = user.id
        event = self._checkout_event(user, event_id="evt_livemode_mismatch_31d")
        event["livemode"] = True
        self._install_stripe_event(event)

        with self._stripe_env():
            response = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=123,v1=valid"},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "stripe_livemode_mismatch")
        refreshed_user = self.db.query(User).filter(User.id == user_id).one()
        self.assertEqual(refreshed_user.plan, "trial")
        self.assertEqual(self.db.query(SubscriptionAuditLog).count(), 0)

    def test_stripe_customer_conflict_rejects_metadata_takeover_and_rolls_back(self):
        user = self._create_user()
        other = User(
            email="owner@example.com",
            password_hash="hash",
            display_name="Owner",
            referral_code="SNBOWNER",
            is_active=True,
            is_verified=True,
            plan="premium",
            plan_status="active",
            stripe_customer_id="cus_sandbox",
            stripe_subscription_id="sub_owner",
        )
        self.db.add(other)
        self.db.commit()
        user_id = user.id
        other_id = other.id
        self._install_stripe_event(self._checkout_event(user, event_id="evt_takeover_31d"))

        with self._stripe_env():
            response = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=123,v1=valid"},
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "stripe_customer_already_linked")
        self.db.expire_all()
        refreshed_user = self.db.query(User).filter(User.id == user_id).one()
        refreshed_other = self.db.query(User).filter(User.id == other_id).one()
        self.assertEqual(refreshed_user.plan, "trial")
        self.assertIsNone(refreshed_user.stripe_customer_id)
        self.assertEqual(refreshed_other.stripe_customer_id, "cus_sandbox")
        self.assertEqual(self.db.query(SubscriptionAuditLog).count(), 0)

    def test_stripe_metadata_user_id_must_be_valid(self):
        user = self._create_user()
        user_id = user.id
        self._install_stripe_event(
            self._checkout_event(
                user,
                event_id="evt_bad_metadata_31d",
                metadata={"user_id": "not-int", "product_id": "premium_br_monthly"},
            )
        )

        with self._stripe_env():
            response = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=123,v1=valid"},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "stripe_metadata_user_id_invalid")
        refreshed_user = self.db.query(User).filter(User.id == user_id).one()
        self.assertEqual(refreshed_user.plan, "trial")
        self.assertEqual(self.db.query(SubscriptionAuditLog).count(), 0)

    def test_state_changing_stripe_events_require_resolved_user_before_audit(self):
        missing_user = SimpleNamespace(id=999999)
        cases = (
            (
                "checkout",
                self._checkout_event(missing_user, event_id="evt_missing_checkout_31d"),
            ),
            (
                "invoice_succeeded",
                self._invoice_event(missing_user, event_id="evt_missing_invoice_31d"),
            ),
            (
                "invoice_failed",
                {
                    "id": "evt_missing_invoice_failed_31d",
                    "livemode": False,
                    "type": "invoice.payment_failed",
                    "data": {
                        "object": {
                            "customer": "cus_missing",
                            "subscription": "sub_missing",
                            "metadata": {"user_id": str(missing_user.id)},
                        }
                    },
                },
            ),
            (
                "subscription_deleted",
                {
                    "id": "evt_missing_subscription_deleted_31d",
                    "livemode": False,
                    "type": "customer.subscription.deleted",
                    "data": {
                        "object": {
                            "customer": "cus_missing",
                            "subscription": "sub_missing",
                            "metadata": {"user_id": str(missing_user.id)},
                        }
                    },
                },
            ),
        )

        for label, event in cases:
            with self.subTest(label=label):
                self._install_stripe_event(event)
                with self._stripe_env():
                    response = self.client.post(
                        "/billing/stripe/webhook",
                        content=b"{}",
                        headers={"stripe-signature": "t=123,v1=valid"},
                    )

                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"], "stripe_user_not_resolved")
                self.assertEqual(self.db.query(SubscriptionAuditLog).count(), 0)
                self.db.rollback()

    def test_downgrade_events_validate_livemode_before_mutation(self):
        user = self._create_user("downgrade-livemode")
        user.plan = "premium"
        user.plan_status = "active"
        user.stripe_customer_id = "cus_downgrade"
        user.stripe_subscription_id = "sub_downgrade"
        self.db.commit()
        user_id = user.id

        cases = (
            {
                "id": "evt_failed_livemode_31d",
                "livemode": True,
                "type": "invoice.payment_failed",
                "data": {
                    "object": {
                        "customer": "cus_downgrade",
                        "subscription": "sub_downgrade",
                        "metadata": {"user_id": str(user.id)},
                    }
                },
            },
            {
                "id": "evt_deleted_livemode_31d",
                "livemode": True,
                "type": "customer.subscription.deleted",
                "data": {
                    "object": {
                        "id": "sub_downgrade",
                        "customer": "cus_downgrade",
                        "metadata": {"user_id": str(user.id)},
                    }
                },
            },
        )

        for event in cases:
            with self.subTest(event_type=event["type"]):
                self._install_stripe_event(event)
                with self._stripe_env():
                    response = self.client.post(
                        "/billing/stripe/webhook",
                        content=b"{}",
                        headers={"stripe-signature": "t=123,v1=valid"},
                    )

                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"], "stripe_livemode_mismatch")
                refreshed = self.db.query(User).filter(User.id == user_id).one()
                self.assertEqual(refreshed.plan, "premium")
                self.assertEqual(refreshed.plan_status, "active")
                self.assertEqual(self.db.query(SubscriptionAuditLog).count(), 0)
                self.db.rollback()

    def test_subscription_deleted_resolves_user_from_subscription_object_id(self):
        user = self._create_user("deleted")
        user.plan = "premium"
        user.plan_status = "active"
        user.stripe_subscription_id = "sub_deleted_31d"
        self.db.commit()
        user_id = user.id

        self._install_stripe_event(
            {
                "id": "evt_deleted_31d",
                "livemode": False,
                "type": "customer.subscription.deleted",
                "data": {
                    "object": {
                        "id": "sub_deleted_31d",
                        "metadata": {},
                    }
                },
            }
        )

        with self._stripe_env():
            response = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=123,v1=valid"},
            )

        self.assertEqual(response.status_code, 200)
        refreshed = self.db.query(User).filter(User.id == user_id).one()
        self.assertEqual(refreshed.plan, "free")
        self.assertEqual(refreshed.plan_status, "premium_inactive")
        self.assertTrue(refreshed.access_app)
        self.assertFalse(refreshed.access_web)
        self.assertFalse(refreshed.access_telegram)
        event = self.db.query(SubscriptionAuditLog).filter(SubscriptionAuditLog.user_id == user_id).one()
        self.assertEqual(event.provider_event_id, "evt_deleted_31d")
        self.assertEqual(event.external_subscription_id, "sub_deleted_31d")

    def test_downgrade_event_rejects_stale_metadata_user_id_takeover(self):
        user = self._create_user("downgrade-takeover")
        user.plan = "premium"
        user.plan_status = "active"
        user.stripe_customer_id = "cus_owner_31d"
        user.stripe_subscription_id = "sub_owner_31d"
        self.db.commit()
        user_id = user.id
        self._install_stripe_event(
            {
                "id": "evt_downgrade_takeover_31d",
                "livemode": False,
                "type": "invoice.payment_failed",
                "data": {
                    "object": {
                        "customer": "cus_attacker_31d",
                        "subscription": "sub_attacker_31d",
                        "metadata": {"user_id": str(user_id)},
                    }
                },
            }
        )

        with self._stripe_env():
            response = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=123,v1=valid"},
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "stripe_customer_mismatch")
        refreshed = self.db.query(User).filter(User.id == user_id).one()
        self.assertEqual(refreshed.plan, "premium")
        self.assertEqual(refreshed.plan_status, "active")
        self.assertEqual(self.db.query(SubscriptionAuditLog).count(), 0)

    def test_downgrade_event_prefers_persisted_stripe_owner_over_metadata(self):
        owner = self._create_user("downgrade-owner")
        attacker = self._create_user("downgrade-metadata")
        owner.plan = "premium"
        owner.plan_status = "active"
        owner.stripe_customer_id = "cus_owner_priority_31d"
        owner.stripe_subscription_id = "sub_owner_priority_31d"
        self.db.commit()
        owner_id = owner.id
        attacker_id = attacker.id
        self._install_stripe_event(
            {
                "id": "evt_downgrade_owner_priority_31d",
                "livemode": False,
                "type": "invoice.payment_failed",
                "data": {
                    "object": {
                        "customer": "cus_owner_priority_31d",
                        "subscription": "sub_owner_priority_31d",
                        "metadata": {"user_id": str(attacker_id)},
                    }
                },
            }
        )

        with self._stripe_env():
            response = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=123,v1=valid"},
            )

        self.assertEqual(response.status_code, 200)
        refreshed_owner = self.db.query(User).filter(User.id == owner_id).one()
        refreshed_attacker = self.db.query(User).filter(User.id == attacker_id).one()
        self.assertEqual(refreshed_owner.plan, "free")
        self.assertEqual(refreshed_owner.plan_status, "premium_inactive")
        self.assertEqual(refreshed_attacker.plan, "trial")
        event = self.db.query(SubscriptionAuditLog).one()
        self.assertEqual(event.user_id, owner_id)

    def test_webhook_secret_missing_fails_closed_without_processing_payload(self):
        user = self._create_user()
        self._install_stripe_event(self._checkout_event(user))

        with self._stripe_env(configured=False):
            response = self.client.post(
                "/billing/stripe/webhook",
                json=self._checkout_event(user),
                headers={"stripe-signature": "t=123,v1=valid"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(user.plan, "trial")
        self.assertEqual(self.db.query(SubscriptionAuditLog).count(), 0)

    def test_webhook_signature_missing_or_invalid_rejects_without_processing(self):
        user = self._create_user()
        valid_event = self._checkout_event(user)

        cases = (
            ("missing_signature", valid_event, None),
            ("invalid_signature", valid_event, "t=123,v1=valid"),
        )

        for label, event, signature in cases:
            with self.subTest(label=label):
                self._install_stripe_event(
                    event if label == "missing_signature" else None,
                    error=ValueError("signature mismatch") if label == "invalid_signature" else None,
                )
                headers = {"stripe-signature": signature} if signature else {}
                with self._stripe_env():
                    response = self.client.post(
                        "/billing/stripe/webhook",
                        json=event,
                        headers=headers,
                    )

                self.assertEqual(response.status_code, 400)

        self.assertEqual(user.plan, "trial")
        self.assertEqual(self.db.query(SubscriptionAuditLog).count(), 0)

    def test_webhook_rejects_oversized_or_invalid_length_before_processing(self):
        user = self._create_user()
        self._install_stripe_event(self._checkout_event(user))

        with self._stripe_env():
            oversized = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={
                    "stripe-signature": "t=123,v1=valid",
                    "content-length": str(stripe_webhook._STRIPE_WEBHOOK_MAX_BYTES + 1),
                },
            )
            invalid_length = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={
                    "stripe-signature": "t=123,v1=valid",
                    "content-length": "not-a-number",
                },
            )

        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(invalid_length.status_code, 400)
        self.assertEqual(user.plan, "trial")
        self.assertEqual(self.db.query(SubscriptionAuditLog).count(), 0)

    def test_read_limited_body_rejects_stream_before_buffering_past_limit(self):
        class StreamingRequest:
            async def stream(self):
                yield b"a" * 4
                yield b"b" * 4
                yield b"c"

        with self.assertRaises(HTTPException) as context:
            asyncio.run(stripe_webhook._read_limited_body(StreamingRequest(), 8))

        self.assertEqual(context.exception.status_code, 413)
        self.assertEqual(context.exception.detail, "stripe_webhook_payload_too_large")

    def test_webhook_max_bytes_env_parser_falls_back_for_invalid_values(self):
        with patch.dict(os.environ, {"STRIPE_WEBHOOK_MAX_BYTES": "not-int"}):
            self.assertEqual(stripe_webhook._positive_int_from_env("STRIPE_WEBHOOK_MAX_BYTES", 262144), 262144)
        with patch.dict(os.environ, {"STRIPE_WEBHOOK_MAX_BYTES": "0"}):
            self.assertEqual(stripe_webhook._positive_int_from_env("STRIPE_WEBHOOK_MAX_BYTES", 262144), 262144)
        with patch.dict(os.environ, {"STRIPE_WEBHOOK_MAX_BYTES": "1024"}):
            self.assertEqual(stripe_webhook._positive_int_from_env("STRIPE_WEBHOOK_MAX_BYTES", 262144), 1024)

    def test_signed_event_without_event_id_or_type_is_rejected(self):
        cases = (
            ("missing_id", {"type": "checkout.session.completed", "data": {"object": {}}}, "stripe_event_id_missing"),
            ("missing_type", {"id": "evt_missing_type", "data": {"object": {}}}, "stripe_event_type_missing"),
        )

        for label, event, detail in cases:
            with self.subTest(label=label):
                self._install_stripe_event(event)
                with self._stripe_env():
                    response = self.client.post(
                        "/billing/stripe/webhook",
                        content=b"{}",
                        headers={"stripe-signature": "t=123,v1=valid"},
                    )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["detail"], detail)
                self.assertEqual(self.db.query(SubscriptionAuditLog).count(), 0)

    def test_replayed_stripe_event_id_does_not_duplicate_financial_effects(self):
        user = self._create_user()
        event = self._checkout_event(user, event_id="evt_replay_31d")
        self._install_stripe_event(event)

        with self._stripe_env():
            first = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=123,v1=valid"},
            )
            second = self.client.post(
                "/billing/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=123,v1=valid"},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json(), {"status": "ok", "duplicate": True})
        self.assertEqual(user.plan, "premium")
        self.assertEqual(
            self.db.query(SubscriptionAuditLog)
            .filter(SubscriptionAuditLog.event_type == "checkout.session.completed")
            .count(),
            1,
        )
        event_log = self.db.query(SubscriptionAuditLog).filter(SubscriptionAuditLog.event_type == "checkout.session.completed").first()
        self.assertEqual(event_log.provider_event_id, "evt_replay_31d")

    def test_concurrent_replayed_stripe_event_id_does_not_duplicate_financial_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(
                f"sqlite:///{tmp}/stripe-concurrent.sqlite",
                connect_args={"check_same_thread": False},
                future=True,
            )
            self.addCleanup(engine.dispose)
            Base.metadata.create_all(bind=engine)
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        CREATE UNIQUE INDEX uq_subscription_audit_provider_event_test
                        ON subscription_audit_logs(provider, provider_event_id)
                        WHERE provider_event_id IS NOT NULL
                        """
                    )
                )
            session_factory = sessionmaker(bind=engine, expire_on_commit=False)
            with session_factory() as setup_db:
                user = User(
                    email="stripe-concurrent@example.com",
                    password_hash="hash",
                    display_name="Stripe Concurrent",
                    referral_code="SNBCONCURRENT",
                    is_active=True,
                    is_verified=True,
                    plan="trial",
                    plan_status="trialing",
                    trial_expires_at=datetime(2026, 6, 14),
                    access_app=True,
                    access_web=True,
                    access_telegram=True,
                )
                setup_db.add(user)
                setup_db.commit()
                user_id = user.id

            event = self._checkout_event(SimpleNamespace(id=user_id), event_id="evt_concurrent_replay_31d")
            self._install_stripe_event(event)
            stripe_webhook.SessionLocal = session_factory

            def post_event():
                return self.client.post(
                    "/billing/stripe/webhook",
                    content=b"{}",
                    headers={"stripe-signature": "t=123,v1=valid"},
                )

            with self._stripe_env(), ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(executor.map(lambda _index: post_event(), range(2)))

            self.assertEqual([response.status_code for response in responses], [200, 200])
            self.assertEqual(
                sum(1 for response in responses if response.json() == {"status": "ok"}),
                1,
            )
            self.assertEqual(
                sum(1 for response in responses if response.json() == {"status": "ok", "duplicate": True}),
                1,
            )
            with session_factory() as verify_db:
                refreshed = verify_db.query(User).filter(User.id == user_id).one()
                self.assertEqual(refreshed.plan, "premium")
                self.assertEqual(refreshed.stripe_customer_id, "cus_sandbox")
                self.assertEqual(refreshed.stripe_subscription_id, "sub_sandbox")
                self.assertEqual(
                    verify_db.query(SubscriptionAuditLog)
                    .filter(
                        SubscriptionAuditLog.event_type == "checkout.session.completed",
                        SubscriptionAuditLog.provider_event_id == "evt_concurrent_replay_31d",
                    )
                    .count(),
                    1,
                )

            engine.dispose()

    def test_different_stripe_event_ids_are_processed_independently(self):
        user = self._create_user()

        with self._stripe_env():
            for event_id in ("evt_first_31d", "evt_second_31d"):
                self._install_stripe_event(self._checkout_event(user, event_id=event_id))
                response = self.client.post(
                    "/billing/stripe/webhook",
                    content=b"{}",
                    headers={"stripe-signature": "t=123,v1=valid"},
                )
                self.assertEqual(response.status_code, 200)

        self.assertEqual(
            self.db.query(SubscriptionAuditLog)
            .filter(SubscriptionAuditLog.event_type == "checkout.session.completed")
            .count(),
            2,
        )


if __name__ == "__main__":
    unittest.main()
