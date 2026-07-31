# ==========================================================
# MISSION 31B - LOGIN SEGURO, EMAIL CODE, SESSAO UNICA
# ==========================================================

import asyncio
import inspect
import logging
import os
import re
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

os.environ.setdefault("SECRET_KEY", "unit-test-secret-key-31b-0123456789abcdef")
os.environ.setdefault("OTP_PEPPER", "unit-test-otp-pepper-31b-0123456789")
os.environ.setdefault("LOGIN_CODE_RESEND_COOLDOWN_SECONDS", "0")

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.auth as auth_mod
import app.social.db as social_db
import app.social.comments as social_comments
import app.social.likes as social_likes
import app.social.moderation as moderation
import app.social.posts as social_posts
import app.social.reposts as social_reposts
from app.api import routes_feed as social_feed_routes
from app.core import settings as core_settings
from app.core.csrf import csrf_rejection
from app.database import Base, get_db
from app.models import AuthAuditEvent, LoginChallenge, SocialComment, SocialLike, SocialPost, SocialRepost, User, UserSession
from app.security import ALGORITHM, create_access_token, get_jwt_secret, hash_password
from app.services import auth_audit_service as auth_audit
from app.services import email_service
from app.services.auth_session_service import (
    CHALLENGE_PURPOSE_EMAIL_CHANGE,
    CHALLENGE_PURPOSE_LOGIN,
    DELIVERY_FAILED,
    DELIVERY_INVALIDATED,
    DELIVERY_PENDING,
    DELIVERY_SENT,
    SESSION_REPLACED_REASON,
    build_login_code_digest,
    consume_login_challenge,
    create_user_session,
    generate_login_code,
    mark_challenge_delivery,
    request_login_code,
    revoke_all_sessions,
    start_login_challenge,
)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_user(db, email, plan="trial", password="123456"):
    now = _utcnow()
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name="Teste",
        is_active=True,
        is_verified=True,
        plan=plan,
        plan_status="active" if plan != "trial" else "trialing",
        access_app=True,
        access_web=True,
        access_telegram=True,
        referral_code=f"SNB{abs(hash(email)) % 10_000_000}",
        created_at=now,
        updated_at=now,
        accepted_terms_at=now,
        accepted_privacy_at=now,
        accepted_risk_notice_at=now,
        trial_expires_at=now + timedelta(days=30),
        plan_expires_at=now + timedelta(days=30) if plan in {"premium", "enterprise"} else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class _MemoryDbTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(
            bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False
        )
        self.db = self.SessionLocal()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()


# ==========================================================
# OTP PRIMITIVES
# ==========================================================

class OtpPrimitivesTests(unittest.TestCase):
    def test_generate_login_code_is_six_digits_with_leading_zeros(self):
        for _ in range(500):
            code = generate_login_code()
            self.assertRegex(code, r"^\d{6}$")

        with mock.patch("secrets.randbelow", return_value=7):
            self.assertEqual(generate_login_code(), "000007")

        with mock.patch("secrets.randbelow", return_value=999_999):
            self.assertEqual(generate_login_code(), "999999")

    def test_generate_login_code_uses_csprng(self):
        with mock.patch("secrets.randbelow", return_value=123) as randbelow:
            generate_login_code()

        randbelow.assert_called_once_with(1_000_000)

    def test_digest_binds_purpose_and_challenge_id(self):
        base = build_login_code_digest(challenge_id="c1", purpose="LOGIN", code="123456", pepper="p" * 16)
        other_purpose = build_login_code_digest(challenge_id="c1", purpose="EMAIL_CHANGE", code="123456", pepper="p" * 16)
        other_challenge = build_login_code_digest(challenge_id="c2", purpose="LOGIN", code="123456", pepper="p" * 16)
        other_pepper = build_login_code_digest(challenge_id="c1", purpose="LOGIN", code="123456", pepper="q" * 16)

        self.assertNotEqual(base, other_purpose)
        self.assertNotEqual(base, other_challenge)
        self.assertNotEqual(base, other_pepper)
        self.assertRegex(base, r"^[0-9a-f]{64}$")

    def test_digest_requires_pepper_without_empty_fallback(self):
        with self.assertRaises(RuntimeError):
            build_login_code_digest(challenge_id="c1", purpose="LOGIN", code="123456", pepper="")

    def test_pepper_fails_closed_in_production(self):
        for environment in ("prod", "production"):
            for pepper in ("", "change_this_pepper"):
                with self.subTest(environment=environment, pepper=pepper):
                    with mock.patch.dict(
                        os.environ,
                        {"ENV": environment, "OTP_PEPPER": pepper},
                    ):
                        with self.assertRaises(RuntimeError):
                            core_settings.get_otp_pepper()

    def test_runtime_validation_blocks_test_mailbox_in_production(self):
        for environment in ("prod", "production"):
            env = {
                "ENV": environment,
                "OTP_PEPPER": "prod-pepper-0123456789abcdef",
                "AUTH_EMAIL_TEST_MAILBOX": "/tmp/m36-mailbox.jsonl",
            }
            with self.subTest(environment=environment):
                with mock.patch.dict(os.environ, env):
                    with self.assertRaises(RuntimeError):
                        core_settings.validate_runtime_security_settings()

    def test_runtime_validation_blocks_insecure_cookie_in_production(self):
        for environment in ("prod", "production"):
            env = {
                "ENV": environment,
                "OTP_PEPPER": "prod-pepper-0123456789abcdef",
                "AUTH_EMAIL_TEST_MAILBOX": "",
                "SESSION_COOKIE_SECURE": "false",
            }
            with self.subTest(environment=environment):
                with mock.patch.dict(os.environ, env):
                    with self.assertRaises(RuntimeError) as ctx:
                        core_settings.validate_runtime_security_settings()

                self.assertIn("SESSION_COOKIE_SECURE", str(ctx.exception))

                # Explicit true (or unset) keeps production startup healthy.
                env["SESSION_COOKIE_SECURE"] = "true"
                with mock.patch.dict(os.environ, env):
                    core_settings.validate_runtime_security_settings()

    def test_production_aliases_use_host_only_secure_cookie_defaults(self):
        for environment in ("prod", "production"):
            with self.subTest(environment=environment):
                with mock.patch.dict(
                    os.environ,
                    {
                        "ENV": environment,
                        "SESSION_COOKIE_NAME": "",
                    },
                ):
                    with mock.patch.dict(os.environ, {}, clear=False):
                        os.environ.pop("SESSION_COOKIE_SECURE", None)
                        self.assertEqual(
                            core_settings.session_cookie_name(),
                            "__Host-snb_session",
                        )
                        self.assertTrue(core_settings.session_cookie_secure())

    def test_websocket_cookie_origin_guard(self):
        from types import SimpleNamespace

        from app.api.routes_chat import _cookie_websocket_origin_allowed

        def fake_ws(origin):
            return SimpleNamespace(headers={"origin": origin} if origin else {})

        with mock.patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "http://localhost:3000"}):
            self.assertTrue(_cookie_websocket_origin_allowed(fake_ws("http://localhost:3000")))
            self.assertFalse(_cookie_websocket_origin_allowed(fake_ws("https://evil.example.com")))
            self.assertFalse(_cookie_websocket_origin_allowed(fake_ws(None)))
            # Wildcard must never authorize credentialed handshakes.
            with mock.patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "*"}):
                self.assertFalse(_cookie_websocket_origin_allowed(fake_ws("https://evil.example.com")))

    def test_email_delivery_mode_never_uses_test_mailbox_in_production(self):
        for environment in ("prod", "production"):
            with self.subTest(environment=environment):
                with mock.patch.dict(
                    os.environ,
                    {"ENV": environment, "AUTH_EMAIL_TEST_MAILBOX": "/tmp/m36-mailbox.jsonl"},
                ):
                    with mock.patch.object(email_service, "SMTP_HOST", ""):
                        self.assertEqual(email_service.email_delivery_mode(), "log")
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "^AUTH_EMAIL_TEST_MAILBOX_FORBIDDEN_IN_PRODUCTION$",
                    ):
                        email_service._append_to_test_mailbox({"body": "must-not-write"})


# ==========================================================
# REQUEST CODE FLOW + RATE LIMITS
# ==========================================================

class RequestCodeFlowTests(_MemoryDbTestCase):
    def test_accepted_request_creates_pending_challenge(self):
        user = _make_user(self.db, "code@example.com")
        outcome = request_login_code(self.db, "CODE@example.com ", channel="web")

        self.assertEqual(outcome["status"], "accepted")
        challenge = outcome["challenge"]
        self.assertEqual(challenge.purpose, CHALLENGE_PURPOSE_LOGIN)
        self.assertEqual(challenge.delivery_status, DELIVERY_PENDING)
        self.assertEqual(challenge.user_id, user.id)
        self.assertRegex(outcome["code"], r"^\d{6}$")
        self.assertNotEqual(challenge.code_hash, outcome["code"])
        self.assertNotIn(outcome["code"], challenge.code_hash)

    def test_unknown_email_is_generic_and_creates_no_challenge(self):
        outcome = request_login_code(self.db, "ghost@example.com")

        self.assertEqual(outcome["status"], "unknown_email")
        self.assertEqual(self.db.query(LoginChallenge).count(), 0)
        events = self.db.query(AuthAuditEvent).filter(AuthAuditEvent.event == "login_code_requested").all()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].status, "unknown_email")
        self.assertNotIn("ghost@example.com", str(events[0].email_masked))

    def test_email_send_window_limit_blocks_fourth_send(self):
        _make_user(self.db, "limited@example.com")

        for _ in range(3):
            outcome = request_login_code(self.db, "limited@example.com")
            self.assertEqual(outcome["status"], "accepted")

        blocked = request_login_code(self.db, "limited@example.com")
        self.assertEqual(blocked["status"], "rate_limited")
        self.assertEqual(blocked["reason"], "email_window")

        rate_events = (
            self.db.query(AuthAuditEvent)
            .filter(AuthAuditEvent.event == "login_code_rate_limited")
            .count()
        )
        self.assertEqual(rate_events, 1)

    def test_resend_cooldown_blocks_immediate_retry(self):
        _make_user(self.db, "cooldown@example.com")

        with mock.patch.dict(os.environ, {"LOGIN_CODE_RESEND_COOLDOWN_SECONDS": "60"}):
            first = request_login_code(self.db, "cooldown@example.com")
            self.assertEqual(first["status"], "accepted")

            retry = request_login_code(self.db, "cooldown@example.com")
            self.assertEqual(retry["status"], "rate_limited")
            self.assertEqual(retry["reason"], "resend_cooldown")

    def test_ip_window_limit_blocks_flood(self):
        _make_user(self.db, "target@example.com")
        ip_hash = auth_audit.hash_ip("10.0.0.1")

        with mock.patch.dict(os.environ, {"LOGIN_CODE_MAX_SENDS_PER_IP": "2"}):
            for suffix in ("a", "b"):
                outcome = request_login_code(
                    self.db,
                    f"unknown-{suffix}@example.com",
                    request_ip_hash=ip_hash,
                )
                self.assertEqual(outcome["status"], "unknown_email")

            blocked = request_login_code(
                self.db,
                "target@example.com",
                request_ip_hash=ip_hash,
            )
            self.assertEqual(blocked["status"], "rate_limited")
            self.assertEqual(blocked["reason"], "ip_window")

    def test_new_request_invalidates_previous_challenge(self):
        _make_user(self.db, "resend@example.com")

        first = request_login_code(self.db, "resend@example.com")
        second = request_login_code(self.db, "resend@example.com")

        self.db.refresh(first["challenge"])
        self.assertIsNotNone(first["challenge"].invalidated_at)
        self.assertEqual(first["challenge"].delivery_status, DELIVERY_INVALIDATED)
        self.assertIsNone(second["challenge"].invalidated_at)

    def test_otp_code_never_reaches_logs(self):
        _make_user(self.db, "quiet@example.com")

        with self.assertLogs(level=logging.DEBUG) as captured:
            outcome = request_login_code(self.db, "quiet@example.com")
            # Force at least one log record so assertLogs does not fail.
            logging.getLogger("stocknewsbr.test").info("marker")

        code = outcome["code"]
        joined = "\n".join(captured.output)
        self.assertNotIn(code, joined)

    def test_log_mode_delivery_never_logs_code(self):
        with mock.patch.object(email_service, "SMTP_HOST", ""):
            with mock.patch.dict(os.environ, {"AUTH_EMAIL_TEST_MAILBOX": ""}):
                with self.assertLogs("stocknewsbr.email", level=logging.DEBUG) as captured:
                    result = email_service.send_login_code_email(
                        email="user@example.com",
                        code="123456",
                        plan="trial",
                        channel="web",
                        expires_minutes=10,
                    )

        self.assertEqual(result["mode"], "log")
        self.assertFalse(result["delivered"])
        joined = "\n".join(captured.output)
        self.assertNotIn("123456", joined)
        self.assertNotIn("user@example.com", joined)


# ==========================================================
# VERIFY CODE FLOW
# ==========================================================

class VerifyCodeFlowTests(_MemoryDbTestCase):
    def _challenge(self, email="verify@example.com", mark_sent=True):
        user = _make_user(self.db, email)
        challenge, code = start_login_challenge(self.db, user, channel="web")
        self.db.commit()

        if mark_sent:
            mark_challenge_delivery(self.db, challenge.id, DELIVERY_SENT)
            self.db.refresh(challenge)

        return user, challenge, code

    def test_correct_code_consumes_once(self):
        user, challenge, code = self._challenge()

        resolved, channel, _, _, _ = consume_login_challenge(self.db, challenge.login_token, code)
        self.db.commit()

        self.assertEqual(resolved.id, user.id)
        self.db.refresh(challenge)
        self.assertIsNotNone(challenge.consumed_at)

        with self.assertRaises(ValueError) as ctx:
            consume_login_challenge(self.db, challenge.login_token, code)
        self.assertEqual(str(ctx.exception), "otp_already_used")

    def test_wrong_code_persists_attempt_counter(self):
        _, challenge, _ = self._challenge()

        with self.assertRaises(ValueError) as ctx:
            consume_login_challenge(self.db, challenge.login_token, "000000")
        self.assertEqual(str(ctx.exception), "otp_invalid")

        control = self.SessionLocal()
        try:
            fresh = control.query(LoginChallenge).filter(LoginChallenge.id == challenge.id).first()
            self.assertEqual(fresh.attempt_count, 1)
            self.assertIsNone(fresh.consumed_at)
        finally:
            control.close()

    def test_sixth_attempt_is_blocked_even_with_correct_code(self):
        _, challenge, code = self._challenge()

        for _ in range(5):
            with self.assertRaises(ValueError) as ctx:
                consume_login_challenge(self.db, challenge.login_token, "999998")
            self.assertEqual(str(ctx.exception), "otp_invalid")

        with self.assertRaises(ValueError) as ctx:
            consume_login_challenge(self.db, challenge.login_token, code)
        self.assertEqual(str(ctx.exception), "otp_too_many_attempts")

        self.db.refresh(challenge)
        self.assertEqual(challenge.attempt_count, 6)
        self.assertIsNone(challenge.consumed_at)

    def test_expired_code_is_rejected_and_invalidated(self):
        _, challenge, code = self._challenge()
        self.db.query(LoginChallenge).filter(LoginChallenge.id == challenge.id).update(
            {"expires_at": _utcnow() - timedelta(seconds=1)}
        )
        self.db.commit()

        with self.assertRaises(ValueError) as ctx:
            consume_login_challenge(self.db, challenge.login_token, code)
        self.assertEqual(str(ctx.exception), "otp_expired")

        self.db.refresh(challenge)
        self.assertIsNotNone(challenge.invalidated_at)

    def test_delivery_gating_blocks_pending_failed_and_invalidated(self):
        cases = (
            (DELIVERY_PENDING, "pending@example.com"),
            (DELIVERY_FAILED, "failed@example.com"),
            (DELIVERY_INVALIDATED, "invalidated@example.com"),
        )

        for status, email in cases:
            with self.subTest(delivery_status=status):
                _, challenge, code = self._challenge(email=email, mark_sent=False)
                values = {"delivery_status": status}
                if status == DELIVERY_INVALIDATED:
                    values["invalidated_at"] = _utcnow()
                self.db.query(LoginChallenge).filter(LoginChallenge.id == challenge.id).update(values)
                self.db.commit()

                with self.assertRaises(ValueError) as ctx:
                    consume_login_challenge(self.db, challenge.login_token, code)
                self.assertEqual(str(ctx.exception), "otp_invalid")

    def test_old_code_cannot_consume_new_challenge(self):
        user = _make_user(self.db, "rotate@example.com")
        old_challenge, old_code = start_login_challenge(self.db, user, channel="web")
        self.db.commit()
        mark_challenge_delivery(self.db, old_challenge.id, DELIVERY_SENT)

        new_challenge, _new_code = start_login_challenge(self.db, user, channel="web")
        self.db.commit()
        mark_challenge_delivery(self.db, new_challenge.id, DELIVERY_SENT)

        # Old challenge was invalidated by the new request.
        with self.assertRaises(ValueError):
            consume_login_challenge(self.db, old_challenge.login_token, old_code)

        # Old code does not match the new challenge digest.
        with self.assertRaises(ValueError):
            consume_login_challenge(self.db, new_challenge.login_token, old_code)


# ==========================================================
# CONCURRENCY
# ==========================================================

class ConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tempdir.name) / "mission31b.db"
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False, "timeout": 30},
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(
            bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False
        )
        self.db = self.SessionLocal()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_two_concurrent_verifications_have_single_winner(self):
        user = _make_user(self.db, "race@example.com")
        challenge, code = start_login_challenge(self.db, user, channel="web")
        self.db.commit()
        mark_challenge_delivery(self.db, challenge.id, DELIVERY_SENT)

        barrier = threading.Barrier(2)
        results = []

        def verify():
            session = self.SessionLocal()
            try:
                barrier.wait(timeout=10)
                resolved, *_ = consume_login_challenge(session, challenge.login_token, code)
                create_user_session(session, resolved, channel="web")
                session.commit()
                return "success"
            except ValueError as exc:
                session.rollback()
                return str(exc)
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(verify) for _ in range(2)]
            results = [future.result(timeout=30) for future in futures]

        self.assertEqual(results.count("success"), 1, results)
        self.assertEqual(len(results), 2)

        control = self.SessionLocal()
        try:
            active = (
                control.query(UserSession)
                .filter(UserSession.user_id == user.id)
                .filter(UserSession.revoked_at.is_(None))
                .count()
            )
            self.assertEqual(active, 1)

            fresh = control.query(LoginChallenge).filter(LoginChallenge.id == challenge.id).first()
            self.assertIsNotNone(fresh.consumed_at)
        finally:
            control.close()

    def test_two_concurrent_logins_leave_single_active_session(self):
        user = _make_user(self.db, "twologin@example.com")

        barrier = threading.Barrier(2)

        def do_login(label):
            session = self.SessionLocal()
            try:
                barrier.wait(timeout=10)
                local_user = session.query(User).filter(User.id == user.id).first()
                created = create_user_session(session, local_user, channel="web", device_label=label)
                session.commit()
                return created.session_id
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(do_login, f"tab-{index}") for index in range(2)]
            session_ids = [future.result(timeout=30) for future in futures]

        control = self.SessionLocal()
        try:
            sessions = control.query(UserSession).filter(UserSession.user_id == user.id).all()
            active = [item for item in sessions if item.revoked_at is None]
            revoked = [item for item in sessions if item.revoked_at is not None]

            self.assertEqual(len(sessions), 2)
            self.assertEqual(len(active), 1)
            self.assertEqual(len(revoked), 1)
            self.assertEqual(revoked[0].revoked_reason, SESSION_REPLACED_REASON)
            self.assertIn(active[0].session_id, session_ids)
        finally:
            control.close()

    def test_concurrent_login_code_requests_never_exceed_the_per_email_limit(self):
        # login_code_rate_limit_state() is a plain check-then-act: it COUNTs
        # existing login_code_requested audit rows, and only the caller's own
        # later commit adds a new one. Without a shared lock around the whole
        # check-then-record span, concurrent requests for the same e-mail can
        # all read the same pre-commit count and all pass the check before
        # any of them has recorded its own event, exceeding
        # LOGIN_CODE_MAX_SENDS_PER_EMAIL. request_login_code() now serializes
        # that span through LOGIN_CODE_RATE_LIMIT_LOCK.
        _make_user(self.db, "race-otp@example.com")
        self.db.commit()

        limit = 2
        attempts = 6
        barrier = threading.Barrier(attempts)

        def send():
            session = self.SessionLocal()
            try:
                barrier.wait(timeout=10)
                result = request_login_code(session, "race-otp@example.com")
                return result["status"]
            finally:
                session.close()

        # Patched once, outside the threads: mock.patch mutates a shared
        # module attribute, so entering/exiting it per-thread would itself
        # race and let the real default value leak into a mid-flight thread.
        with mock.patch(
            "app.services.auth_session_service.login_code_max_sends_per_email",
            return_value=limit,
        ):
            with ThreadPoolExecutor(max_workers=attempts) as pool:
                futures = [pool.submit(send) for _ in range(attempts)]
                results = [future.result(timeout=30) for future in futures]

        accepted = results.count("accepted")
        self.assertLessEqual(
            accepted,
            limit,
            f"expected the lock to cap accepted sends at {limit}, got {results}",
        )
        self.assertEqual(accepted, limit, results)

    def test_duplicate_email_is_blocked_by_unique_constraint(self):
        _make_user(self.db, "unique-a@example.com")
        second = _make_user(self.db, "unique-b@example.com")

        second.email = "unique-a@example.com"
        self.db.add(second)

        with self.assertRaises(IntegrityError):
            self.db.commit()

        self.db.rollback()


# ==========================================================
# AUTH ENDPOINTS (cookie, session unica, logout, email change)
# ==========================================================

class _EndpointTestCase(unittest.TestCase):
    ORIGIN = "http://localhost:3000"

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(
            bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False
        )
        self.db = self.SessionLocal()

        self.outbox = []

        def capture(message):
            self.outbox.append(message)
            return True

        email_service.set_delivery_override(capture)

        self._original_auth_sessionlocal = auth_mod.SessionLocal
        auth_mod.SessionLocal = self.SessionLocal

        self.app = self._build_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def tearDown(self):
        email_service.set_delivery_override(None)
        auth_mod.SessionLocal = self._original_auth_sessionlocal
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _build_app(self):
        app = FastAPI()
        app.include_router(auth_mod.router)

        allowed = [self.ORIGIN]

        @app.middleware("http")
        async def csrf_guard(request: Request, call_next):
            rejection = csrf_rejection(request, allowed)
            if rejection is not None:
                return rejection
            return await call_next(request)

        def override_get_db():
            session = self.SessionLocal()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        return app

    def _last_code_for(self, email):
        for message in reversed(self.outbox):
            if message["to"] == email:
                return message["metadata"].get("code")
        return None

    def _login_via_code(self, email, *, channel="web", client=None):
        client = client or self.client
        response = client.post(
            "/auth/request-code",
            json={"email": email, "channel": channel},
            headers={"Origin": self.ORIGIN},
        )
        assert response.status_code == 200, response.text
        login_token = response.json()["login_token"]
        code = self._last_code_for(email)
        verify = client.post(
            "/auth/login/verify-otp",
            json={"login_token": login_token, "code": code, "channel": channel},
            headers={"Origin": self.ORIGIN},
        )
        return verify


class AuthEndpointTests(_EndpointTestCase):
    def test_request_code_is_generic_for_unknown_email(self):
        known_user = _make_user(self.db, "exists@example.com")
        del known_user

        known = self.client.post(
            "/auth/request-code",
            json={"email": "exists@example.com"},
            headers={"Origin": self.ORIGIN},
        )
        unknown = self.client.post(
            "/auth/request-code",
            json={"email": "nobody@example.com"},
            headers={"Origin": self.ORIGIN},
        )

        self.assertEqual(known.status_code, 200)
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(known.json()["detail"], unknown.json()["detail"])
        self.assertTrue(unknown.json()["login_token"])  # decoy token
        self.assertIsNotNone(unknown.json()["otp_expires_at"])

        # Only the real account received an e-mail.
        recipients = [message["to"] for message in self.outbox]
        self.assertIn("exists@example.com", recipients)
        self.assertNotIn("nobody@example.com", recipients)

    def test_otp_never_appears_in_json_responses(self):
        _make_user(self.db, "json@example.com")

        response = self.client.post(
            "/auth/request-code",
            json={"email": "json@example.com"},
            headers={"Origin": self.ORIGIN},
        )
        code = self._last_code_for("json@example.com")

        self.assertNotIn(code, response.text)
        self.assertNotIn("debug_otp_code", response.text)

    def test_web_login_sets_httponly_cookie_and_hides_token(self):
        _make_user(self.db, "webflow@example.com")

        verify = self._login_via_code("webflow@example.com")

        self.assertEqual(verify.status_code, 200, verify.text)
        payload = verify.json()
        self.assertIsNone(payload.get("access_token"))

        set_cookie = verify.headers.get("set-cookie", "")
        cookie_name = core_settings.session_cookie_name()
        self.assertIn(cookie_name, set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("Path=/", set_cookie)
        self.assertIn("SameSite=lax", set_cookie)

        me = self.client.get("/auth/me")
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["email"], "webflow@example.com")

    def test_app_channel_receives_bearer_token_in_json(self):
        _make_user(self.db, "appflow@example.com")

        verify = self._login_via_code("appflow@example.com", channel="app")

        self.assertEqual(verify.status_code, 200, verify.text)
        payload = verify.json()
        self.assertTrue(payload.get("access_token"))
        decoded = jwt.decode(payload["access_token"], get_jwt_secret(), algorithms=[ALGORITHM])
        self.assertIn("sid", decoded)

    def test_password_login_requires_otp_on_every_plan(self):
        # Owner policy: no login path skips the code. The password endpoint
        # must issue an OTP challenge for trial/free accounts too, not only
        # premium.
        for plan in ("trial", "premium", "free"):
            with self.subTest(plan=plan):
                email = f"pwd-{plan}@example.com"
                _make_user(self.db, email, plan=plan)

                response = self.client.post(
                    "/auth/login-json",
                    json={"email": email, "password": "123456", "channel": "web"},
                    headers={"Origin": self.ORIGIN},
                )

                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertTrue(body["otp_required"], body)
                self.assertIsNone(body.get("access_token"))
                self.assertTrue(body["login_token"])

    def test_replayed_code_fails_after_success(self):
        _make_user(self.db, "replay@example.com")

        first = self.client.post(
            "/auth/request-code",
            json={"email": "replay@example.com"},
            headers={"Origin": self.ORIGIN},
        )
        login_token = first.json()["login_token"]
        code = self._last_code_for("replay@example.com")

        ok = self.client.post(
            "/auth/login/verify-otp",
            json={"login_token": login_token, "code": code},
            headers={"Origin": self.ORIGIN},
        )
        self.assertEqual(ok.status_code, 200)

        replay = self.client.post(
            "/auth/login/verify-otp",
            json={"login_token": login_token, "code": code},
            headers={"Origin": self.ORIGIN},
        )
        self.assertEqual(replay.status_code, 400)
        self.assertEqual(replay.json()["detail"], "otp_already_used")

    def test_new_login_replaces_previous_session(self):
        user = _make_user(self.db, "single@example.com")

        tab_a = TestClient(self.app, raise_server_exceptions=False)
        verify_a = self._login_via_code("single@example.com", client=tab_a)
        self.assertEqual(verify_a.status_code, 200)

        me_a = tab_a.get("/auth/me")
        self.assertEqual(me_a.status_code, 200)

        tab_b = TestClient(self.app, raise_server_exceptions=False)
        verify_b = self._login_via_code("single@example.com", client=tab_b)
        self.assertEqual(verify_b.status_code, 200)

        # Tab A lost its session with the replacement detail.
        me_a_after = tab_a.get("/auth/me")
        self.assertEqual(me_a_after.status_code, 401)
        self.assertEqual(me_a_after.json()["detail"], "session_replaced")

        control = self.SessionLocal()
        try:
            active = (
                control.query(UserSession)
                .filter(UserSession.user_id == user.id)
                .filter(UserSession.revoked_at.is_(None))
                .count()
            )
            self.assertEqual(active, 1)
        finally:
            control.close()

    def test_logout_is_idempotent_and_does_not_revive(self):
        _make_user(self.db, "logout@example.com")

        verify = self._login_via_code("logout@example.com")
        self.assertEqual(verify.status_code, 200)

        first = self.client.post("/auth/logout", headers={"Origin": self.ORIGIN})
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["ok"])

        me = self.client.get("/auth/me")
        self.assertEqual(me.status_code, 401)

        # Repeated logout stays safe even without a valid session.
        second = self.client.post("/auth/logout", headers={"Origin": self.ORIGIN})
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["ok"])

    def test_logout_all_revokes_every_session(self):
        user = _make_user(self.db, "logoutall@example.com")

        # Extra bearer session (e.g. app) plus the web session.
        extra_session = create_user_session(self.db, user, channel="app")
        self.db.commit()
        del extra_session

        verify = self._login_via_code("logoutall@example.com")
        self.assertEqual(verify.status_code, 200)

        response = self.client.post("/auth/logout-all", headers={"Origin": self.ORIGIN})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        control = self.SessionLocal()
        try:
            active = (
                control.query(UserSession)
                .filter(UserSession.user_id == user.id)
                .filter(UserSession.revoked_at.is_(None))
                .count()
            )
            self.assertEqual(active, 0)
        finally:
            control.close()

        me = self.client.get("/auth/me")
        self.assertEqual(me.status_code, 401)

    def test_csrf_blocks_cookie_requests_with_foreign_origin(self):
        _make_user(self.db, "csrf@example.com")
        verify = self._login_via_code("csrf@example.com")
        self.assertEqual(verify.status_code, 200)

        attack = self.client.post(
            "/auth/logout-all",
            headers={"Origin": "https://evil.example.com"},
        )
        self.assertEqual(attack.status_code, 403)
        self.assertEqual(attack.json()["detail"], "csrf_origin_rejected")

        missing_origin = self.client.post("/auth/logout-all")
        self.assertEqual(missing_origin.status_code, 403)

        legit = self.client.post("/auth/logout-all", headers={"Origin": self.ORIGIN})
        self.assertEqual(legit.status_code, 200)

    def test_bearer_clients_are_not_blocked_by_csrf(self):
        user = _make_user(self.db, "bearer@example.com")
        session = create_user_session(self.db, user, channel="app")
        self.db.commit()
        token = create_access_token({"sub": str(user.id), "sid": session.session_id})

        bare_client = TestClient(self.app, raise_server_exceptions=False)
        response = bare_client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)


class TokenHardeningTests(_EndpointTestCase):
    def _session_token(self, email="tokens@example.com", plan="trial"):
        user = _make_user(self.db, email, plan=plan)
        session = create_user_session(self.db, user, channel="app")
        self.db.commit()
        token = create_access_token({"sub": str(user.id), "sid": session.session_id})
        return user, session, token

    def _me(self, token):
        return self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    def test_valid_session_token_is_accepted(self):
        _, _, token = self._session_token()
        self.assertEqual(self._me(token).status_code, 200)

    def test_token_without_sid_is_rejected_for_all_plans(self):
        for plan, email in (("free", "free-sidless@example.com"), ("premium", "prem-sidless@example.com")):
            with self.subTest(plan=plan):
                user = _make_user(self.db, email, plan=plan)
                token = create_access_token({"sub": str(user.id)})
                self.assertEqual(self._me(token).status_code, 401)

    def test_alg_none_token_is_rejected(self):
        user, session, _ = self._session_token("algnone@example.com")
        payload = {"sub": str(user.id), "sid": session.session_id}
        none_token = jwt.encode(payload, "", algorithm=None) if False else None

        # python-jose refuses to build alg=none tokens; craft one manually.
        import base64
        import json as jsonlib

        def b64(data):
            return base64.urlsafe_b64encode(jsonlib.dumps(data).encode()).rstrip(b"=").decode()

        crafted = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(payload)}."
        del none_token
        self.assertEqual(self._me(crafted).status_code, 401)

    def test_wrong_algorithm_token_is_rejected(self):
        user, session, _ = self._session_token("hs384@example.com")
        crafted = jwt.encode(
            {"sub": str(user.id), "sid": session.session_id},
            get_jwt_secret(),
            algorithm="HS384",
        )
        self.assertEqual(self._me(crafted).status_code, 401)

    def test_tampered_signature_is_rejected(self):
        _, _, token = self._session_token("tampered@example.com")
        tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
        self.assertEqual(self._me(tampered).status_code, 401)

    def test_expired_token_is_rejected(self):
        user, session, _ = self._session_token("expired@example.com")
        expired = jwt.encode(
            {
                "sub": str(user.id),
                "sid": session.session_id,
                "exp": datetime.utcnow() - timedelta(minutes=5),
                "iat": datetime.utcnow() - timedelta(minutes=10),
            },
            get_jwt_secret(),
            algorithm=ALGORITHM,
        )
        self.assertEqual(self._me(expired).status_code, 401)

    def test_sub_mismatch_with_session_owner_is_rejected(self):
        user, session, _ = self._session_token("owner@example.com")
        other = _make_user(self.db, "intruder@example.com")
        forged = create_access_token({"sub": str(other.id), "sid": session.session_id})
        del user
        self.assertEqual(self._me(forged).status_code, 401)

    def test_revoked_session_token_is_rejected(self):
        user, session, token = self._session_token("revoked@example.com")
        revoke_all_sessions(self.db, user.id, reason="logout_all")
        self.db.commit()
        del session
        self.assertEqual(self._me(token).status_code, 401)

    def test_expired_server_session_is_rejected(self):
        user, session, token = self._session_token("serverexp@example.com")
        self.db.query(UserSession).filter(UserSession.id == session.id).update(
            {"expires_at": _utcnow() - timedelta(minutes=1)}
        )
        self.db.commit()
        del user
        self.assertEqual(self._me(token).status_code, 401)

    def test_session_token_has_high_entropy_and_no_raw_storage(self):
        user, session, token = self._session_token("entropy@example.com")
        self.assertGreaterEqual(len(session.session_id), 40)
        # Raw JWT never persisted server-side.
        control = self.SessionLocal()
        try:
            rows = control.query(UserSession).filter(UserSession.user_id == user.id).all()
            for row in rows:
                for value in (row.session_id, row.device_label or "", row.revoked_reason or ""):
                    self.assertNotIn(token, value)
        finally:
            control.close()


class MassAssignmentAndConsentTests(_EndpointTestCase):
    def test_profile_rejects_forbidden_fields(self):
        _make_user(self.db, "massassign@example.com")
        verify = self._login_via_code("massassign@example.com")
        self.assertEqual(verify.status_code, 200)

        forbidden_payloads = (
            {"role": "admin"},
            {"is_admin": True},
            {"admin": True},
            {"official": True},
            {"verified": True},
            {"is_bot": True},
            {"premium": True},
            {"plan": "premium"},
            {"subscription_status": "active"},
            {"user_id": 999},
            {"session_generation": 5},
            {"active_session_id": "x"},
            {"email": "hacker@example.com"},
        )

        for payload in forbidden_payloads:
            with self.subTest(payload=payload):
                response = self.client.patch(
                    "/auth/profile",
                    json={"display_name": "Novo", **payload},
                    headers={"Origin": self.ORIGIN},
                )
                self.assertEqual(response.status_code, 422, response.text)

    def test_profile_allowlist_fields_are_updated(self):
        _make_user(self.db, "profile@example.com")
        verify = self._login_via_code("profile@example.com")
        self.assertEqual(verify.status_code, 200)

        response = self.client.patch(
            "/auth/profile",
            json={"display_name": "Trader BR", "avatar_url": "/media/avatars/a.png", "phone": "11 90000-0000"},
            headers={"Origin": self.ORIGIN},
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["display_name"], "Trader BR")
        self.assertEqual(payload["email"], "profile@example.com")

    def test_register_requires_explicit_consents(self):
        missing = self.client.post(
            "/auth/register",
            json={"email": "new@example.com", "password": "supersegura"},
        )
        self.assertEqual(missing.status_code, 422)

        refused = self.client.post(
            "/auth/register",
            json={
                "email": "new@example.com",
                "password": "supersegura",
                "accepted_terms": True,
                "accepted_privacy": True,
                "accepted_risk_notice": False,
            },
        )
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.json()["detail"], "legal_acceptance_required")

        accepted = self.client.post(
            "/auth/register",
            json={
                "email": "new@example.com",
                "password": "supersegura",
                "accepted_terms": True,
                "accepted_privacy": True,
                "accepted_risk_notice": True,
            },
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)

        control = self.SessionLocal()
        try:
            user = control.query(User).filter(User.email == "new@example.com").first()
            self.assertIsNotNone(user.accepted_terms_at)
            self.assertIsNotNone(user.accepted_privacy_at)
            self.assertIsNotNone(user.accepted_risk_notice_at)
        finally:
            control.close()

    def test_login_does_not_overwrite_consent_timestamps(self):
        user = _make_user(self.db, "consent@example.com")
        original = user.accepted_terms_at

        verify = self._login_via_code("consent@example.com")
        self.assertEqual(verify.status_code, 200)

        control = self.SessionLocal()
        try:
            fresh = control.query(User).filter(User.id == user.id).first()
            self.assertEqual(fresh.accepted_terms_at, original)
        finally:
            control.close()


class EmailChangeTests(_EndpointTestCase):
    def _login(self, email="owner@example.com"):
        _make_user(self.db, email)
        verify = self._login_via_code(email)
        self.assertEqual(verify.status_code, 200)

    def _request_change(self, new_email):
        return self.client.post(
            "/auth/email-change/request",
            json={"new_email": new_email},
            headers={"Origin": self.ORIGIN},
        )

    def _verify_change(self, login_token, code):
        return self.client.post(
            "/auth/email-change/verify",
            json={"login_token": login_token, "code": code},
            headers={"Origin": self.ORIGIN},
        )

    def test_anonymous_request_is_rejected(self):
        response = TestClient(self.app, raise_server_exceptions=False).post(
            "/auth/email-change/request",
            json={"new_email": "x@example.com"},
        )
        self.assertEqual(response.status_code, 401)

    def test_same_email_is_rejected(self):
        self._login("same@example.com")
        response = self._request_change("same@example.com")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "email_change_same_email")

    def test_invalid_format_is_rejected(self):
        self._login("fmt@example.com")
        response = self._request_change("not-an-email")
        self.assertEqual(response.status_code, 422)

    def test_full_flow_updates_email_and_notifies_old_address(self):
        self._login("before@example.com")

        request = self._request_change("after@example.com")
        self.assertEqual(request.status_code, 200, request.text)
        login_token = request.json()["login_token"]
        code = self._last_code_for("after@example.com")
        self.assertIsNotNone(code)

        verify = self._verify_change(login_token, code)
        self.assertEqual(verify.status_code, 200, verify.text)
        self.assertEqual(verify.json()["email"], "after@example.com")

        notices = [m for m in self.outbox if m["kind"] == "email_change_notice"]
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0]["to"], "before@example.com")

        # Current session survives (policy: revoke all OTHER sessions).
        me = self.client.get("/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "after@example.com")

        # Replay of the same challenge fails.
        replay = self._verify_change(login_token, code)
        self.assertEqual(replay.status_code, 400)

    def test_wrong_code_expired_and_wrong_purpose_are_rejected(self):
        self._login("matrix@example.com")

        request = self._request_change("matrix-new@example.com")
        login_token = request.json()["login_token"]
        code = self._last_code_for("matrix-new@example.com")

        wrong = self._verify_change(login_token, "000001" if code != "000001" else "000002")
        self.assertEqual(wrong.status_code, 400)

        # Wrong purpose: a LOGIN challenge token cannot be used here.
        login_request = self.client.post(
            "/auth/request-code",
            json={"email": "matrix@example.com"},
            headers={"Origin": self.ORIGIN},
        )
        login_challenge_token = login_request.json()["login_token"]
        login_code = self._last_code_for("matrix@example.com")
        cross = self._verify_change(login_challenge_token, login_code)
        self.assertEqual(cross.status_code, 400)

        # Expired challenge.
        control = self.SessionLocal()
        try:
            control.query(LoginChallenge).filter(LoginChallenge.login_token == login_token).update(
                {"expires_at": _utcnow() - timedelta(seconds=1)}
            )
            control.commit()
        finally:
            control.close()

        expired = self._verify_change(login_token, code)
        self.assertEqual(expired.status_code, 400)
        self.assertEqual(expired.json()["detail"], "otp_expired")

    def test_wrong_owner_cannot_consume_challenge(self):
        self._login("victim@example.com")
        request = self._request_change("victim-new@example.com")
        login_token = request.json()["login_token"]
        code = self._last_code_for("victim-new@example.com")

        # A different user logs in on another client and tries to consume it.
        attacker_client = TestClient(self.app, raise_server_exceptions=False)
        _make_user(self.db, "attacker@example.com")
        attacker_login = self._login_via_code("attacker@example.com", client=attacker_client)
        self.assertEqual(attacker_login.status_code, 200)

        stolen = attacker_client.post(
            "/auth/email-change/verify",
            json={"login_token": login_token, "code": code},
            headers={"Origin": self.ORIGIN},
        )
        self.assertEqual(stolen.status_code, 400)
        self.assertEqual(stolen.json()["detail"], "otp_invalid")

    def test_taken_email_fails_without_partial_state(self):
        _make_user(self.db, "holder@example.com")
        self._login("wants@example.com")

        request = self._request_change("holder@example.com")
        self.assertEqual(request.status_code, 200)
        login_token = request.json()["login_token"]
        code = self._last_code_for("holder@example.com")

        verify = self._verify_change(login_token, code)
        self.assertEqual(verify.status_code, 400)
        self.assertEqual(verify.json()["detail"], "email_change_failed")

        control = self.SessionLocal()
        try:
            self.assertEqual(
                control.query(User).filter(User.email == "holder@example.com").count(),
                1,
            )
            self.assertEqual(
                control.query(User).filter(User.email == "wants@example.com").count(),
                1,
            )
            # email_changed must NOT be audited when the update rolled back.
            changed_events = (
                control.query(AuthAuditEvent)
                .filter(AuthAuditEvent.event == "email_changed")
                .count()
            )
            self.assertEqual(changed_events, 0)
        finally:
            control.close()

    def test_profile_patch_cannot_bypass_email_change(self):
        self._login("bypass@example.com")
        response = self.client.patch(
            "/auth/profile",
            json={"email": "sneaky@example.com"},
            headers={"Origin": self.ORIGIN},
        )
        self.assertEqual(response.status_code, 422)

    def test_rate_limit_applies_to_email_change_requests(self):
        self._login("ratelimited@example.com")

        with mock.patch.dict(os.environ, {"LOGIN_CODE_MAX_SENDS_PER_EMAIL": "1"}):
            first = self._request_change("rl-target@example.com")
            self.assertEqual(first.status_code, 200)

            second = self._request_change("rl-target@example.com")
            self.assertEqual(second.status_code, 429)


class AuditPrivacyTests(_EndpointTestCase):
    def test_audit_trail_contains_no_secrets_and_masks_email(self):
        _make_user(self.db, "audited@example.com")

        request = self.client.post(
            "/auth/request-code",
            json={"email": "audited@example.com"},
            headers={"Origin": self.ORIGIN},
        )
        login_token = request.json()["login_token"]
        code = self._last_code_for("audited@example.com")
        verify = self.client.post(
            "/auth/login/verify-otp",
            json={"login_token": login_token, "code": code},
            headers={"Origin": self.ORIGIN},
        )
        self.assertEqual(verify.status_code, 200)

        control = self.SessionLocal()
        try:
            events = control.query(AuthAuditEvent).all()
            self.assertTrue(events)

            event_names = {event.event for event in events}
            self.assertIn("login_code_requested", event_names)
            self.assertIn("login_code_sent", event_names)
            self.assertIn("login_code_verified", event_names)
            self.assertIn("session_created", event_names)
            self.assertIn("login_success", event_names)

            session_row = control.query(UserSession).filter(UserSession.revoked_at.is_(None)).first()

            for event in events:
                blob = "|".join(
                    str(value)
                    for value in (
                        event.email_masked,
                        event.email_hash,
                        event.ip_hash,
                        event.user_agent,
                        event.sid_ref,
                        event.reason,
                        event.status,
                        event.correlation_id,
                    )
                )
                self.assertNotIn(code, blob)
                self.assertNotIn(login_token, blob)
                self.assertNotIn(session_row.session_id, blob)
                self.assertNotIn("audited@example.com", blob)
        finally:
            control.close()

    def test_login_success_requires_session(self):
        _make_user(self.db, "nosession@example.com")

        request = self.client.post(
            "/auth/request-code",
            json={"email": "nosession@example.com"},
            headers={"Origin": self.ORIGIN},
        )
        login_token = request.json()["login_token"]

        bad = self.client.post(
            "/auth/login/verify-otp",
            json={"login_token": login_token, "code": "000000"},
            headers={"Origin": self.ORIGIN},
        )
        self.assertEqual(bad.status_code, 400)

        control = self.SessionLocal()
        try:
            success_events = (
                control.query(AuthAuditEvent)
                .filter(AuthAuditEvent.event == "login_success")
                .count()
            )
            sessions = control.query(UserSession).count()
            self.assertEqual(success_events, 0)
            self.assertEqual(sessions, 0)
        finally:
            control.close()


# ==========================================================
# SOCIAL PROTECTION
# ==========================================================

class SocialProtectionTests(unittest.TestCase):
    ORIGIN = "http://localhost:3000"

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(
            bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False
        )
        self.db = self.SessionLocal()

        self.tempdir = tempfile.TemporaryDirectory()
        self._original_moderation_path = moderation.MODERATION_STORE_PATH
        moderation.MODERATION_STORE_PATH = Path(self.tempdir.name) / "moderation_state.json"

        self._patched_sessionlocals = []
        for module in (social_posts, social_comments, social_likes, social_reposts):
            self._patched_sessionlocals.append((module, module.SessionLocal))
            module.SessionLocal = self.SessionLocal

        self._original_social_initialized = social_db._initialized
        social_db._initialized = True

        from app.api import routes_feed, routes_likes

        app = FastAPI()
        app.include_router(routes_feed.router)
        app.include_router(routes_likes.router)

        def override_get_db():
            session = self.SessionLocal()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        self.app = app
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        moderation.MODERATION_STORE_PATH = self._original_moderation_path
        for module, original in self._patched_sessionlocals:
            module.SessionLocal = original
        social_db._initialized = self._original_social_initialized
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        self.tempdir.cleanup()

    def _bearer(self, email="social@example.com"):
        user = _make_user(self.db, email)
        session = create_user_session(self.db, user, channel="web")
        self.db.commit()
        token = create_access_token({"sub": str(user.id), "sid": session.session_id})
        return user, {"Authorization": f"Bearer {token}", "Origin": self.ORIGIN}

    def test_mutable_social_actions_require_authentication(self):
        cases = (
            ("POST", "/ticker/PETR4/post", {"text": "sem login"}),
            ("POST", "/post/1/comment", {"text": "sem login"}),
            ("POST", "/post/1/repost", {}),
            ("DELETE", "/post/1", None),
            ("POST", "/post/1/like", None),
            ("POST", "/post/1/unlike", None),
        )

        for method, url, body in cases:
            with self.subTest(url=url):
                response = self.client.request(method, url, json=body)
                self.assertEqual(response.status_code, 401, f"{url}: {response.text}")

    def test_authenticated_post_passes_guardian_and_persists(self):
        _, headers = self._bearer("poster@example.com")

        response = self.client.post(
            "/ticker/PETR4/post",
            json={"text": "Analise tecnica do papel segue construtiva."},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("id", response.json())

    def test_guardian_blocks_forbidden_content_for_authenticated_users(self):
        _, headers = self._bearer("guardian@example.com")

        forbidden_samples = (
            "acesse https://golpe.example.com agora",
            "me chama no whatsapp 11 99999-9999",
            "meu email é contato@gmail.com",
            "aposta garantida no tigrinho",
        )

        for text in forbidden_samples:
            with self.subTest(text=text):
                response = self.client.post(
                    "/ticker/PETR4/post",
                    json={"text": text},
                    headers=headers,
                )
                self.assertEqual(response.status_code, 429, response.text)

    def test_ownership_enforced_on_delete(self):
        _, owner_headers = self._bearer("owner-social@example.com")

        created = self.client.post(
            "/ticker/PETR4/post",
            json={"text": "post do dono"},
            headers=owner_headers,
        )
        post_id = created.json()["id"]

        _, other_headers = self._bearer("other-social@example.com")
        forbidden = self.client.delete(f"/post/{post_id}", headers=other_headers)
        self.assertEqual(forbidden.status_code, 403)

        allowed = self.client.delete(f"/post/{post_id}", headers=owner_headers)
        self.assertEqual(allowed.status_code, 200)

    def test_feed_orders_post_3_post_2_post_1_with_id_tiebreaker(self):
        user, _ = self._bearer("feed-order@example.com")
        older = datetime(2026, 1, 1, 12, 0, 0)
        newer = datetime(2026, 1, 1, 13, 0, 0)
        rows = [
            SocialPost(user_id=user.id, ticker="PETR4", text="post 1", created_at=older),
            SocialPost(user_id=user.id, ticker="PETR4", text="post 2", created_at=newer),
            SocialPost(user_id=user.id, ticker="PETR4", text="post 3", created_at=newer),
        ]
        self.db.add_all(rows)
        self.db.commit()

        with mock.patch.object(
            social_posts,
            "get_user_guardian_scores",
            return_value={user.id: {"score": 100, "label": "Verde"}},
        ), mock.patch.object(social_posts, "get_hidden_post_ids", return_value=set()):
            posts = social_posts.get_posts("PETR4")

        self.assertEqual([post["text"] for post in posts], ["post 3", "post 2", "post 1"])
        source = inspect.getsource(social_posts.get_posts)
        self.assertIn("SocialPost.created_at.desc(), SocialPost.id.desc()", source)
        self.assertNotIn("reverse(", source)

    def test_comments_stay_with_their_post_persist_media_and_hide_email(self):
        user, _ = self._bearer("public-email@example.com")
        posts = [
            SocialPost(user_id=user.id, ticker="PETR4", text="post 1", display_name=user.email),
            SocialPost(user_id=user.id, ticker="PETR4", text="post 2", display_name=user.email),
        ]
        self.db.add_all(posts)
        self.db.commit()
        gif_url = "https://media.tenor.com/comment.gif"
        comment = social_comments.add_comment(
            posts[1].id,
            user.id,
            "🐂 comentário",
            image_url=gif_url,
            display_name=user.email,
            email=user.email,
        )

        first = social_comments.get_comments_for_posts([posts[0].id, posts[1].id])
        second = social_comments.get_comments_for_posts([posts[0].id, posts[1].id])

        self.assertEqual(first[posts[0].id], [])
        self.assertEqual(first[posts[1].id], [comment])
        self.assertEqual(second, first)
        self.assertEqual(comment["post_id"], posts[1].id)
        self.assertEqual(comment["image_url"], gif_url)
        self.assertEqual(comment["user"], "Trader")
        self.assertNotIn("user_email", comment)
        self.assertNotIn("email", comment)
        public_post = social_posts._serialize_post(posts[0], guardian_score={"score": 100, "label": "Verde"})
        self.assertEqual(public_post["user"], "Trader")
        self.assertNotIn("user_email", public_post)
        self.assertNotIn("email", public_post)

    def test_delete_post_removes_dependents_and_moderator_is_authorized(self):
        owner, _ = self._bearer("dependent-owner@example.com")
        moderator, _ = self._bearer("social-moderator@example.com")
        moderator.role = "moderator"
        self.db.commit()
        post = SocialPost(user_id=owner.id, ticker="PETR4", text="with dependencies")
        self.db.add(post)
        self.db.commit()
        self.db.add_all([
            SocialComment(post_id=post.id, user_id=owner.id, text="comment"),
            SocialLike(post_id=post.id, user_id=owner.id),
            SocialRepost(post_id=post.id, user_id=owner.id, quote_text="quote"),
        ])
        self.db.commit()

        self.assertTrue(social_posts.delete_post(post.id, moderator.id, can_moderate=True))
        for model in (SocialPost, SocialComment, SocialLike, SocialRepost):
            self.assertEqual(self.db.query(model).count(), 0)

    def test_delete_route_grants_moderator_role(self):
        moderator, _ = self._bearer("route-moderator@example.com")
        moderator.role = "moderator"
        with mock.patch.object(social_feed_routes, "get_post", return_value={"id": 7, "ticker": "PETR4"}), mock.patch.object(
            social_feed_routes, "delete_post", return_value=True
        ) as delete, mock.patch.object(social_feed_routes, "broadcast_ticker_event", new=mock.AsyncMock()):
            response = asyncio.run(social_feed_routes.delete_ticker_post(7, current_user=moderator))

        self.assertEqual(response, {"status": "deleted", "post_id": 7})
        delete.assert_called_once_with(7, moderator.id, can_moderate=True)

    def test_revoked_session_cannot_post(self):
        user, headers = self._bearer("revoked-social@example.com")
        revoke_all_sessions(self.db, user.id, reason="logout_all")
        self.db.commit()

        response = self.client.post(
            "/ticker/PETR4/post",
            json={"text": "não deveria entrar"},
            headers=headers,
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
