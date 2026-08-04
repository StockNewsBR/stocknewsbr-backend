"""
Testes focados de atomicidade para Missão 31D.

Comprovam:
- apply_referral_validation não executa commit/rollback internos
- validate_referrals (wrapper legado) mantém commit/rollback
- Fluxo Stripe: commit único atômico
- Fluxo Stripe: rollback completo em falha
- subscription_sync: commit único atômico
- subscription_sync: rollback completo em falha
- IntegrityError genérico: apenas conflito de event_id retorna duplicate=true
- Erro em referrals não retorna HTTP 200 silencioso
"""
import os
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, event, text
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app import auth as auth_mod
    from app.api import stripe_webhook
    from app.database import Base
    from app.models import Referral, ReferralStats, SubscriptionAuditLog, User
    from app.services.referrals import apply_referral_validation, validate_referrals

    IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    IMPORT_ERROR = exc


class ReferralFixtureMixin:
    """Helpers compartilhados para cenarios reais de referral."""

    def _user(self, email, name, code, plan="premium", plan_expires_at=None):
        user = User(
            email=email,
            password_hash="hash",
            display_name=name,
            referral_code=code,
            is_active=True,
            is_verified=True,
            plan=plan,
            plan_status="active" if plan == "premium" else "trialing",
            plan_expires_at=plan_expires_at,
            trial_expires_at=self.now + timedelta(days=30) if plan == "trial" else None,
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


@unittest.skipIf(IMPORT_ERROR is not None, f"runtime dependency unavailable: {IMPORT_ERROR}")
class ReferralAtomicityTests(ReferralFixtureMixin, unittest.TestCase):
    """Testes de atomicidade da validação de referrals."""

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
        self.now = datetime(2026, 5, 14, 12, 0, 0)

    def tearDown(self):
        self.db.close()

    def _add_flush_failure_once(self):
        state = {"raised": False}

        def fail_once(_session, _flush_context, _instances):
            if state["raised"]:
                return
            state["raised"] = True
            raise SQLAlchemyError("forced referral validation flush failure")

        event.listen(self.db, "before_flush", fail_once)
        self.addCleanup(lambda: event.remove(self.db, "before_flush", fail_once))

    def test_apply_referral_validation_no_commit(self):
        """apply_referral_validation NÃO executa commit."""
        referrer = self._user("joao@example.com", "Joao Silva", "SNBJOAO", plan="premium")
        referrer.plan_expires_at = self.now + timedelta(days=30)
        for i in range(1, 4):
            self._paid_referral(referrer, i, paid_days_ago=8)
        self.db.commit()

        initial_expiry = referrer.plan_expires_at
        # Chamar apply_referral_validation - não deve persistir sem commit externo
        result = apply_referral_validation(self.db, now=self.now)

        # Sem commit externo, as alterações estão apenas na sessão (flush não foi chamado)
        # Mas para testar se não comita, verificamos se o resultado é retornado
        self.assertEqual(result["validated"], 3)
        self.assertEqual(result["processed_referrers"], 1)

        # As alterações estão pendentes na sessão, mas não comitadas
        # Fazendo rollback, devem ser descartadas
        self.db.rollback()

        # Após rollback, nada deve ter persistido
        referral = self.db.query(Referral).first()
        self.assertEqual(referral.status, "pending")
        stats = self.db.query(ReferralStats).filter(ReferralStats.user_id == referrer.id).first()
        # Se stats foi criado antes do rollback, deve ter voltado ao estado anterior (total_validated=0)
        if stats is not None:
            self.assertEqual(stats.total_validated, 0)
        # plan_expires_at não deve ter sido estendido
        self.assertEqual(referrer.plan_expires_at, initial_expiry)

    def test_apply_referral_validation_no_rollback(self):
        """apply_referral_validation NÃO executa rollback - propaga exceção."""
        referrer = self._user("joao@example.com", "Joao Silva", "SNBJOAO", plan="premium")
        referrer.plan_expires_at = self.now + timedelta(days=30)
        for i in range(1, 4):
            self._paid_referral(referrer, i, paid_days_ago=8)
        self.db.commit()

        self._add_flush_failure_once()

        with self.assertRaises(SQLAlchemyError):
            apply_referral_validation(self.db, now=self.now)

        self.assertTrue(self.db.in_transaction())
        self.db.rollback()
        referral = self.db.query(Referral).first()
        self.assertEqual(referral.status, "pending")

    def test_validate_referrals_legacy_commits_on_success(self):
        """validate_referrals (wrapper) executa commit no sucesso."""
        referrer = self._user("joao@example.com", "Joao Silva", "SNBJOAO", plan="premium")
        referrer.plan_expires_at = self.now + timedelta(days=30)
        for i in range(1, 4):
            self._paid_referral(referrer, i, paid_days_ago=8)
        self.db.commit()

        result = validate_referrals(self.db, now=self.now)

        self.assertEqual(result["validated"], 3)
        self.assertEqual(result["processed_referrers"], 1)
        self.assertNotIn("error", result)

        # Verifica se persistiu (sem rollback manual)
        referral = self.db.query(Referral).first()
        self.assertEqual(referral.status, "validated")
        stats = self.db.query(ReferralStats).filter(ReferralStats.user_id == referrer.id).first()
        self.assertEqual(stats.total_validated, 3)
        self.assertEqual(stats.benefit_level, 1)

    def test_validate_referrals_legacy_rollsback_on_error(self):
        """validate_referrals (wrapper) executa rollback em SQLAlchemyError."""
        referrer = self._user("joao@example.com", "Joao Silva", "SNBJOAO", plan="premium")
        referrer.plan_expires_at = self.now + timedelta(days=30)
        initial_expiry = referrer.plan_expires_at
        for i in range(1, 4):
            self._paid_referral(referrer, i, paid_days_ago=8)
        self.db.commit()
        self._add_flush_failure_once()

        original_commit = self.db.commit
        original_rollback = self.db.rollback
        commit_count = [0]
        rollback_count = [0]

        def counting_commit():
            commit_count[0] += 1
            original_commit()

        def counting_rollback():
            rollback_count[0] += 1
            original_rollback()

        self.db.commit = counting_commit
        self.db.rollback = counting_rollback

        result = validate_referrals(self.db, now=self.now)

        self.assertEqual(commit_count[0], 0)
        self.assertEqual(rollback_count[0], 1)
        self.assertEqual(result["validated"], 0)
        self.assertEqual(result["error"], "database_error")
        referral = self.db.query(Referral).first()
        self.assertEqual(referral.status, "pending")
        stats = self.db.query(ReferralStats).filter(ReferralStats.user_id == referrer.id).first()
        if stats is not None:
            self.assertEqual(stats.total_validated, 0)
        self.assertEqual(referrer.plan_expires_at, initial_expiry)

    def test_validate_referrals_legacy_rollsback_and_reraises_unexpected_error(self):
        """validate_referrals faz rollback também em erro inesperado."""
        referrer = self._user("maria@example.com", "Maria Silva", "SNBMARIA", plan="premium")
        referrer.plan_expires_at = self.now + timedelta(days=30)
        self.db.commit()

        original_rollback = self.db.rollback
        rollback_count = [0]

        def counting_rollback():
            rollback_count[0] += 1
            original_rollback()

        self.db.rollback = counting_rollback
        self.addCleanup(lambda: setattr(self.db, "rollback", original_rollback))

        with patch("app.services.referrals.apply_referral_validation", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                validate_referrals(self.db, now=self.now)

        self.assertEqual(rollback_count[0], 1)


@unittest.skipIf(IMPORT_ERROR is not None, f"runtime dependency unavailable: {IMPORT_ERROR}")
class StripeWebhookAtomicityTests(unittest.TestCase):
    """Testes de atomicidade do webhook Stripe."""

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
        self.now = datetime(2026, 5, 14, 12, 0, 0)
        self.original_session_local = stripe_webhook.SessionLocal
        self.original_stripe = stripe_webhook._STRIPE
        self.original_stripe_webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
        stripe_webhook.SessionLocal = lambda: self.db

        self.event_id = "evt_checkout_31d"
        self.event = {
            "id": self.event_id,
            "livemode": False,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "mode": "subscription",
                    "payment_status": "paid",
                    "status": "complete",
                    "customer": "cus_sandbox",
                    "subscription": {"id": "sub_sandbox", "status": "active"},
                    "product": {"id": "premium_br_monthly"},
                    "customer_email": "stripe@example.com",
                    "phone": "+5511999999999",
                    "card_last4": "4242",
                    "metadata": {"user_id": "1", "product_id": "premium_br_monthly"},
                }
            },
        }

        def construct_event(payload, signature, secret):
            self.assertEqual(secret, "whsec_test_31d")
            self.assertEqual(signature, "t=123,v1=valid")
            return self.event

        stripe_webhook._STRIPE = SimpleNamespace(
            Webhook=SimpleNamespace(construct_event=construct_event)
        )

        app = FastAPI()
        app.include_router(stripe_webhook.router)
        self.client = TestClient(app, raise_server_exceptions=False)

        os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_31d"

        self.user = User(
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
        self.db.add(self.user)
        self.db.commit()
        self.user_id = self.user.id
        self.event["data"]["object"]["metadata"]["user_id"] = str(self.user_id)

    def tearDown(self):
        stripe_webhook.SessionLocal = self.original_session_local
        stripe_webhook._STRIPE = self.original_stripe
        if self.original_stripe_webhook_secret is None:
            os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
        else:
            os.environ["STRIPE_WEBHOOK_SECRET"] = self.original_stripe_webhook_secret
        self.db.close()

    def _make_request(self):
        return self.client.post(
            "/billing/stripe/webhook",
            content=b"{}",
            headers={"stripe-signature": "t=123,v1=valid"},
        )

    def _paid_referral_for_referrer(self, referrer, index, paid_days_ago=8):
        referred = User(
            email=f"stripe-paid{index}@example.com",
            password_hash="hash",
            display_name=f"Cliente {index}",
            referral_code=f"SNBSTRP{index}",
            is_active=True,
            is_verified=True,
            plan="premium",
            plan_status="active",
            plan_expires_at=self.now + timedelta(days=250),
            access_app=True,
            access_web=True,
            access_telegram=True,
        )
        self.db.add(referred)
        self.db.flush()
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

    def _referral_reward_scenario(self):
        referrer = User(
            email="stripe-referrer@example.com",
            password_hash="hash",
            display_name="Stripe Referrer",
            referral_code="SNBSTRREF",
            is_active=True,
            is_verified=True,
            plan="premium",
            plan_status="active",
            plan_expires_at=self.now + timedelta(days=250),
            access_app=True,
            access_web=True,
            access_telegram=True,
        )
        self.db.add(referrer)
        self.db.flush()
        initial_expiry = referrer.plan_expires_at
        self.db.add(
            ReferralStats(
                user_id=referrer.id,
                total_validated=0,
                total_active=0,
                benefit_level=0,
                reward_balance_months=0,
            )
        )
        for index in range(1, 4):
            self._paid_referral_for_referrer(referrer, index, paid_days_ago=8)
        self.db.commit()
        return referrer.id, initial_expiry

    def _install_referrer_plan_update_failure(self, referrer_id: int):
        self.db.execute(
            text(
                f"""
                CREATE TRIGGER fail_referrer_plan_extension_31d
                BEFORE UPDATE OF plan_expires_at ON users
                WHEN OLD.id = {int(referrer_id)}
                BEGIN
                    SELECT RAISE(ABORT, 'forced_referrer_plan_extension_failure');
                END
                """
            )
        )
        self.db.commit()

    def test_stripe_single_commit_on_success(self):
        """Fluxo Stripe: exatamente um commit em sucesso."""
        # Rastrear chamadas de commit
        original_commit = self.db.commit
        commit_count = [0]

        def counting_commit():
            commit_count[0] += 1
            original_commit()

        self.db.commit = counting_commit

        response = self._make_request()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        # Deve ter exatamente 1 commit
        self.assertEqual(commit_count[0], 1, f"Expected 1 commit, got {commit_count[0]}")

        # Verificar estado final persistido
        self.assertEqual(self.user.plan, "premium")
        audit_log = self.db.query(SubscriptionAuditLog).filter(
            SubscriptionAuditLog.provider_event_id == self.event_id
        ).first()
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.event_type, "checkout.session.completed")

    def test_stripe_referral_failure_rolls_back_user_audit_referral_stats_and_expiry(self):
        """Fluxo Stripe: falha real em referrals reverte todo o efeito financeiro."""
        referrer_id, initial_expiry = self._referral_reward_scenario()
        self._install_referrer_plan_update_failure(referrer_id)
        self.event["id"] = "evt_referral_failure_31d"

        response = self._make_request()

        self.assertEqual(response.status_code, 500)
        self.db.expire_all()
        user = self.db.query(User).filter(User.id == self.user_id).one()
        referrer = self.db.query(User).filter(User.id == referrer_id).one()
        stats = self.db.query(ReferralStats).filter(ReferralStats.user_id == referrer_id).one()

        self.assertEqual(user.plan, "trial")
        self.assertEqual(user.plan_status, "trialing")
        self.assertIsNone(user.stripe_customer_id)
        self.assertIsNone(user.stripe_subscription_id)
        self.assertIsNone(user.plan_expires_at)
        self.assertEqual(referrer.plan_expires_at, initial_expiry)
        self.assertEqual(stats.total_validated, 0)
        self.assertEqual(stats.reward_balance_months, 0)
        self.assertEqual(
            self.db.query(Referral).filter(Referral.status == "validated").count(),
            0,
        )
        self.assertIsNone(
            self.db.query(SubscriptionAuditLog)
            .filter(SubscriptionAuditLog.provider_event_id == "evt_referral_failure_31d")
            .first()
        )

    def test_stripe_duplicate_event_returns_duplicate_true(self):
        """Conflito real de provider_event_id retorna 200 com duplicate=true."""
        response1 = self._make_request()
        self.assertEqual(response1.status_code, 200)

        response2 = self._make_request()
        self.assertEqual(response2.status_code, 200)
        self.assertTrue(response2.json().get("duplicate"))

        # Apenas 1 audit log
        count = self.db.query(SubscriptionAuditLog).filter(
            SubscriptionAuditLog.provider_event_id == self.event_id
        ).count()
        self.assertEqual(count, 1)

    def test_stripe_different_integrity_error_not_duplicate(self):
        """IntegrityError real de origem diferente não retorna duplicate=true."""
        self.event["id"] = "evt_non_duplicate_integrity_31d"
        self.db.execute(
            text(
                """
                CREATE TRIGGER fail_audit_insert_31d
                BEFORE INSERT ON subscription_audit_logs
                WHEN NEW.provider_event_id = 'evt_non_duplicate_integrity_31d'
                BEGIN
                    SELECT RAISE(ABORT, 'forced_non_event_integrity_failure');
                END
                """
            )
        )
        self.db.commit()

        response = self._make_request()

        self.assertEqual(response.status_code, 500)
        self.db.expire_all()
        user = self.db.query(User).filter(User.id == self.user_id).one()
        self.assertEqual(user.plan, "trial")
        self.assertEqual(
            self.db.query(SubscriptionAuditLog)
            .filter(SubscriptionAuditLog.provider_event_id == "evt_non_duplicate_integrity_31d")
            .count(),
            0,
        )


@unittest.skipIf(IMPORT_ERROR is not None, f"runtime dependency unavailable: {IMPORT_ERROR}")
class SubscriptionSyncAtomicityTests(ReferralFixtureMixin, unittest.TestCase):
    """Testes de atomicidade do subscription_sync."""

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
        self.now = datetime(2026, 5, 14, 12, 0, 0)

    def tearDown(self):
        self.db.close()

    def _subscription_client(self, current_user, raise_server_exceptions=True):
        app = FastAPI()
        app.include_router(auth_mod.router)

        def override_get_db():
            try:
                yield self.db
            finally:
                if self.db.in_transaction():
                    self.db.rollback()

        def override_current_user():
            return current_user

        app.dependency_overrides[auth_mod.get_db] = override_get_db
        app.dependency_overrides[auth_mod.get_current_user] = override_current_user
        return TestClient(app, raise_server_exceptions=raise_server_exceptions)

    def _referral_reward_scenario(self):
        referrer = self._user("joao@example.com", "Joao Silva", "SNBJOAO", plan="premium")
        referrer.plan_expires_at = self.now + timedelta(days=250)
        initial_expiry = referrer.plan_expires_at
        self.db.add(
            ReferralStats(
                user_id=referrer.id,
                total_validated=0,
                total_active=0,
                benefit_level=0,
                reward_balance_months=0,
            )
        )
        for i in range(1, 4):
            self._paid_referral(referrer, i, paid_days_ago=8)
        return referrer.id, initial_expiry

    def _install_referrer_plan_update_failure(self, referrer_id: int):
        self.db.execute(
            text(
                f"""
                CREATE TRIGGER fail_subscription_referrer_plan_extension_31d
                BEFORE UPDATE OF plan_expires_at ON users
                WHEN OLD.id = {int(referrer_id)}
                BEGIN
                    SELECT RAISE(ABORT, 'forced_subscription_referrer_plan_extension_failure');
                END
                """
            )
        )
        self.db.commit()

    def test_subscription_sync_safe_downgrade_single_commit_and_sanitized_audit(self):
        """subscription_sync: rota real permite downgrade seguro com um commit e payload sanitizado."""
        current_user = self._user("sync@example.com", "Sync User", "SNBSYNC", plan="premium")
        current_user.plan_status = "active"
        current_user.plan_expires_at = self.now + timedelta(days=30)
        sentinel = "purchase-token-SENTINEL-31D-never-persist"
        self.db.commit()

        original_commit = self.db.commit
        commit_count = [0]

        def counting_commit():
            commit_count[0] += 1
            original_commit()

        self.db.commit = counting_commit
        client = self._subscription_client(current_user)

        response = client.post(
            "/auth/subscription/sync",
            json={
                "activate": False,
                "provider": "google_play",
                "product_id": "premium_br_monthly",
                "origin": "android_app",
                "external_subscription_id": "sub_test",
                "purchase_token": sentinel,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(commit_count[0], 1)
        self.assertEqual(current_user.plan, "free")
        self.assertEqual(current_user.plan_status, "premium_inactive")
        self.assertIsNone(current_user.plan_expires_at)
        self.assertIsNone(current_user.google_play_purchase_token)
        self.assertTrue(current_user.access_app)
        self.assertFalse(current_user.access_web)
        self.assertFalse(current_user.access_telegram)
        audit = self.db.query(SubscriptionAuditLog).filter(
            SubscriptionAuditLog.event_type == "subscription_sync"
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.status, "premium_inactive")
        self.assertNotIn(sentinel, audit.payload_excerpt or "")
        self.assertNotIn("purchase_token", audit.payload_excerpt or "")
        self.assertNotIn(sentinel, response.text)

    def test_subscription_sync_activation_without_provider_verifier_fails_closed_before_mutation(self):
        """subscription_sync: active=true sem verificador real falha fechado e nao persiste efeitos."""
        current_user = self._user("sync@example.com", "Sync User", "SNBSYNC", plan="trial")
        referrer_id, initial_expiry = self._referral_reward_scenario()
        self.db.commit()
        current_user_id = current_user.id
        sentinel = "purchase-token-SENTINEL-31D-blocked"
        original_commit = self.db.commit
        commit_count = [0]

        def counting_commit():
            commit_count[0] += 1
            original_commit()

        self.db.commit = counting_commit
        client = self._subscription_client(current_user, raise_server_exceptions=False)

        response = client.post(
            "/auth/subscription/sync",
            json={
                "activate": True,
                "provider": "google_play",
                "product_id": "premium_br_monthly",
                "origin": "android_app",
                "external_subscription_id": "sub_test",
                "purchase_token": sentinel,
            },
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "subscription_provider_verification_unavailable")
        self.assertEqual(commit_count[0], 0)
        self.db.expire_all()
        user = self.db.query(User).filter(User.id == current_user_id).one()
        referrer = self.db.query(User).filter(User.id == referrer_id).one()
        stats = self.db.query(ReferralStats).filter(ReferralStats.user_id == referrer_id).one()

        self.assertEqual(user.plan, "trial")
        self.assertEqual(user.plan_status, "trialing")
        self.assertIsNone(user.plan_expires_at)
        self.assertIsNone(user.google_play_purchase_token)
        self.assertEqual(referrer.plan_expires_at, initial_expiry)
        self.assertEqual(stats.total_validated, 0)
        self.assertEqual(stats.reward_balance_months, 0)
        self.assertEqual(
            self.db.query(Referral).filter(Referral.status == "validated").count(),
            0,
        )
        self.assertEqual(
            self.db.query(SubscriptionAuditLog)
            .filter(SubscriptionAuditLog.event_type == "subscription_sync")
            .count(),
            0,
        )
        self.assertNotIn(sentinel, response.text)


@unittest.skipIf(IMPORT_ERROR is not None, f"runtime dependency unavailable: {IMPORT_ERROR}")
class ReferralWorkerLegacyTests(ReferralFixtureMixin, unittest.TestCase):
    """Testes para garantir que referral_worker continua funcionando com wrapper legado."""

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
        self.now = datetime(2026, 5, 14, 12, 0, 0)

    def tearDown(self):
        self.db.close()

    def test_validate_referrals_legacy_works_for_worker(self):
        """O wrapper validate_referrals continua funcionando para worker isolado."""
        referrer = self._user("joao@example.com", "Joao Silva", "SNBJOAO", plan="premium")
        referrer.plan_expires_at = self.now + timedelta(days=30)
        for i in range(1, 4):
            self._paid_referral(referrer, i, paid_days_ago=8)
        self.db.commit()

        # Simular worker: nova session, chamada validate_referrals (que comita internamente)
        db2 = self.Session()
        try:
            result = validate_referrals(db2, now=self.now)
            self.assertEqual(result["validated"], 3)
            self.assertFalse(db2.in_transaction())
        except SQLAlchemyError:
            db2.rollback()
            raise
        finally:
            db2.close()

        # Verificar em nova session
        db3 = self.Session()
        try:
            stats = db3.query(ReferralStats).filter(ReferralStats.user_id == referrer.id).first()
            self.assertEqual(stats.total_validated, 3)
            self.assertEqual(stats.benefit_level, 1)
        finally:
            db3.close()


if __name__ == "__main__":
    unittest.main()
