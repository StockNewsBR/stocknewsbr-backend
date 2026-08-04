# ==========================================================
# MISSION 31B.1 — Official accounts, official bot, anti-impersonation
# ==========================================================
import os

os.environ.setdefault("SECRET_KEY", "unit-test-secret-31b1-0123456789abcdef")
os.environ.setdefault("OTP_PEPPER", "unit-test-otp-pepper-31b1-0123456789")
os.environ.setdefault("ENV", "test")

import unittest

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import register
from app.database import Base
from app.database_schema import SCHEMA_PATCHES
from app.models import User, UserSession
from app.schemas import UserProfileUpdateRequest, UserRegister
from app.security import hash_password, verify_password
from app.services.access_service import serialize_user_access
from app.services.auth_session_service import create_user_session
from app.services import auth_audit_service as auth_audit
from app.services.official_identity_service import (
    OFFICIAL_ACCOUNT,
    OFFICIAL_BOT,
    OfficialIdentityConflictError,
    ROLE_BOT,
    ROLE_OFFICIAL,
    assert_bot_content_allowed,
    ensure_official_identities,
    user_is_official,
)
from app.social.identity_guard import (
    check_impersonation,
    is_official_link,
    is_reserved_identity,
)


def _mk_user(**kw):
    base = dict(
        email=kw.pop("email", "u@example.com"),
        password_hash="x",
        referral_code="REF12345",
        is_active=True,
        is_verified=True,
    )
    base.update(kw)
    return User(**base)


class DbCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()


# ----------------------------------------------------------
# Anti-impersonation (tests 1, 2, 3, 12)
# ----------------------------------------------------------
class ImpersonationTests(unittest.TestCase):
    def test_01_reserved_username_is_blocked(self):
        for name in ["stocknewsbr", "stocknewsbr_bot", "admin", "suporte", "system", "snbr"]:
            with self.subTest(name=name):
                self.assertTrue(is_reserved_identity(name))
                self.assertIsNotNone(check_impersonation(username=name))

    def test_02_display_name_official_impersonation_is_blocked(self):
        for name in ["StockNewsBR Oficial", "StockNewsBR Suporte", "Conta Oficial", "Admin Oficial"]:
            with self.subTest(name=name):
                self.assertIsNotNone(check_impersonation(display_name=name))

    def test_reserved_role_words_with_spaces_are_blocked(self):
        for name in [
            "Suporte Trader",
            "Admin Trader",
            "Sistema Trader",
            "Bot Trader",
            "Oficial Trader",
        ]:
            with self.subTest(name=name):
                self.assertTrue(is_reserved_identity(name), name)
                self.assertIsNotNone(check_impersonation(display_name=name))

    def test_reserved_role_words_in_camel_case_are_blocked(self):
        for name in [
            "TeamOficial",
            "StaffOficial",
            "AdminTrader",
            "SuporteTrader",
            "SistemaTrader",
            "BotTrader",
            "OficialTrader",
            "StockNewsBROficial",
        ]:
            with self.subTest(name=name):
                self.assertTrue(is_reserved_identity(name), name)
                self.assertIsNotNone(check_impersonation(display_name=name))

    def test_03_normalization_blocks_case_space_accent_punctuation(self):
        for name in [
            "S T O C K N E W S B R",
            "stock.news.br",
            "stock-news-br",
            "stock_news_br",
            "StöckNéwsBR",
            "  STOCKNEWSBR  ",
            "oficial",
            "OFICIAL",
        ]:
            with self.subTest(name=name):
                self.assertTrue(is_reserved_identity(name), name)

    def test_12_homoglyph_and_invisible_chars_do_not_bypass(self):
        cyrillic = "SтockNewsBR"      # Cyrillic т
        invisible = "stock​news‍br"  # zero-width chars
        fullwidth = "ＳtockNewsBR"      # full-width S
        for name in [cyrillic, invisible, fullwidth]:
            with self.subTest(name=repr(name)):
                self.assertTrue(is_reserved_identity(name), repr(name))

    def test_11_verified_emoji_alone_is_not_reserved(self):
        # A lone verified emoji is not an identity and must not be "reserved".
        self.assertFalse(is_reserved_identity("✅"))
        self.assertFalse(is_reserved_identity("Joana ✅"))
        # But a verified emoji cannot smuggle the brand past the gate.
        self.assertTrue(is_reserved_identity("StockNewsBR ✅"))

    def test_clean_identities_are_allowed(self):
        for name in ["Joana Trader", "Investidor PETR4", "Maria Silva", "day trader br"]:
            with self.subTest(name=name):
                self.assertFalse(is_reserved_identity(name))
                self.assertIsNone(check_impersonation(display_name=name))

    def test_privileged_identity_is_exempt(self):
        self.assertIsNone(check_impersonation(display_name="StockNewsBR Oficial", is_privileged=True))


# ----------------------------------------------------------
# Payload hardening (tests 4, 5, 6, 7, 19)
# ----------------------------------------------------------
class PayloadHardeningTests(unittest.TestCase):
    def test_04_05_06_07_profile_update_rejects_sensitive_fields(self):
        for payload in [
            {"official": True},
            {"verified": True},
            {"is_verified": True},
            {"role": "admin"},
            {"role": "official"},
            {"role": "bot"},
            {"is_bot": True},
            {"is_admin": True},
            {"scopes": ["*"]},
            {"permissions": ["*"]},
            {"badges": ["official"]},
        ]:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    UserProfileUpdateRequest(**payload)

    def test_19_register_payload_cannot_escalate_identity(self):
        # UserRegister silently drops unknown/sensitive fields -> no escalation.
        model = UserRegister(
            email="x@example.com",
            password="secret123",
            accepted_terms=True,
            accepted_privacy=True,
            accepted_risk_notice=True,
            official=True,
            role="admin",
            is_bot=True,
            is_admin=True,
        )
        for field in ("official", "role", "is_bot", "is_admin"):
            self.assertFalse(hasattr(model, field), field)

    def test_20_prior_31b_contract_still_valid(self):
        # Normal profile update still works.
        ok = UserProfileUpdateRequest(display_name="Nome Novo", phone="11999998888")
        self.assertEqual(ok.display_name, "Nome Novo")


# ----------------------------------------------------------
# Official account + bot (tests 8, 9, 10, 18) — real backend flags
# ----------------------------------------------------------
class OfficialIdentityTests(DbCase):
    def test_register_rejects_official_service_email(self):
        for spec in (OFFICIAL_ACCOUNT, OFFICIAL_BOT):
            with self.subTest(email=spec["email"]):
                payload = UserRegister(
                    email=spec["email"],
                    password="secret123",
                    display_name="Trader Limpo",
                    accepted_terms=True,
                    accepted_privacy=True,
                    accepted_risk_notice=True,
                )
                with self.assertRaises(HTTPException) as ctx:
                    register(payload, self.db)
                self.assertEqual(ctx.exception.status_code, 400)
                self.assertEqual(ctx.exception.detail, "official_email_reserved")
                self.assertEqual(self.db.query(User).filter(User.email == spec["email"]).count(), 0)

    def test_08_official_account_has_official_and_verified(self):
        ids = ensure_official_identities(self.db)
        official = ids["official"]
        self.assertTrue(official.official)
        self.assertTrue(official.is_verified)
        self.assertEqual(official.role, ROLE_OFFICIAL)
        self.assertFalse(official.is_bot)
        self.assertTrue(user_is_official(official))

    def test_09_official_bot_has_role_bot_and_is_bot(self):
        ids = ensure_official_identities(self.db)
        bot = ids["bot"]
        self.assertEqual(bot.role, ROLE_BOT)
        self.assertTrue(bot.is_bot)
        self.assertTrue(bot.official)

    def test_seed_is_idempotent(self):
        ensure_official_identities(self.db)
        ensure_official_identities(self.db)
        count = self.db.query(User).filter(User.official.is_(True)).count()
        self.assertEqual(count, 2)

    def test_seed_rejects_preexisting_public_official_email(self):
        public_user = _mk_user(
            email=OFFICIAL_ACCOUNT["email"],
            password_hash=hash_password("attackerpass123"),
            display_name="Trader Limpo",
            is_verified=True,
            official=False,
            role="user",
            is_bot=False,
            official_identity_locked=False,
        )
        self.db.add(public_user)
        self.db.commit()

        with self.assertRaises(OfficialIdentityConflictError):
            ensure_official_identities(self.db)

        self.db.rollback()
        row = self.db.query(User).filter(User.email == OFFICIAL_ACCOUNT["email"]).one()
        self.assertFalse(row.official)
        self.assertEqual(row.role, "user")
        self.assertFalse(row.is_bot)
        self.assertFalse(row.official_identity_locked)
        self.assertTrue(verify_password("attackerpass123", row.password_hash))

    def test_seed_rejects_preexisting_public_bot_email(self):
        public_user = _mk_user(
            email=OFFICIAL_BOT["email"],
            password_hash=hash_password("attackerpass123"),
            display_name="Trader Limpo",
            is_verified=True,
            official=False,
            role="user",
            is_bot=False,
            official_identity_locked=False,
        )
        self.db.add(public_user)
        self.db.commit()

        with self.assertRaises(OfficialIdentityConflictError):
            ensure_official_identities(self.db)

        self.db.rollback()
        row = self.db.query(User).filter(User.email == OFFICIAL_BOT["email"]).one()
        self.assertFalse(row.official)
        self.assertEqual(row.role, "user")
        self.assertFalse(row.is_bot)
        self.assertFalse(row.official_identity_locked)
        self.assertTrue(verify_password("attackerpass123", row.password_hash))

    def test_seed_reconciles_locked_identity_and_revokes_sessions(self):
        official = _mk_user(
            email=OFFICIAL_ACCOUNT["email"],
            password_hash=hash_password("oldofficialpass"),
            display_name="Nome Antigo",
            is_verified=True,
            official=True,
            role=ROLE_OFFICIAL,
            is_bot=False,
            official_identity_locked=True,
        )
        self.db.add(official)
        self.db.flush()
        active_session = create_user_session(self.db, official, channel="web")
        self.db.commit()

        ids = ensure_official_identities(self.db)

        row = ids["official"]
        self.assertEqual(row.id, official.id)
        self.assertEqual(row.display_name, OFFICIAL_ACCOUNT["display_name"])
        self.assertEqual(row.password_hash, "!")
        self.assertTrue(row.official_identity_locked)

        session_row = self.db.query(UserSession).filter(UserSession.id == active_session.id).one()
        self.assertIsNotNone(session_row.revoked_at)
        self.assertEqual(session_row.revoked_reason, "official_identity_seed_reconciled")

    def test_10_badge_depends_on_backend_flag_not_name(self):
        # Regular user whose NAME looks official but flag is false -> no badge.
        liar = _mk_user(email="liar@example.com", display_name="StockNewsBR Oficial")
        self.db.add(liar)
        self.db.commit()
        self.assertFalse(user_is_official(liar))
        data = serialize_user_access(liar)
        self.assertFalse(data["official"])
        self.assertEqual(data["role"], "user")
        self.assertFalse(data["is_bot"])

    def test_10b_official_serializes_badge_true(self):
        ids = ensure_official_identities(self.db)
        data = serialize_user_access(ids["official"])
        self.assertTrue(data["official"])
        self.assertTrue(data["verified"])
        self.assertEqual(data["role"], ROLE_OFFICIAL)


# ----------------------------------------------------------
# Bot least privilege (tests 13, 14, 15)
# ----------------------------------------------------------
class BotGuardTests(unittest.TestCase):
    def test_13_bot_cannot_emit_trade_signals(self):
        for text in ["BUY PETR4", "sell now", "SHORT VALE3", "cover position", "compra forte", "venda já"]:
            with self.subTest(text=text):
                self.assertEqual(
                    assert_bot_content_allowed(text, has_source=True),
                    "bot_trade_signal_forbidden",
                )

    def test_14_bot_cannot_publish_news_without_source(self):
        self.assertEqual(
            assert_bot_content_allowed("Comunicado institucional neutro", has_source=False),
            "bot_content_requires_source",
        )

    def test_15_bot_cannot_fire_operational_alert_before_m32(self):
        self.assertEqual(
            assert_bot_content_allowed("alerta operacional agora", has_source=True),
            "bot_operational_alert_forbidden_before_mission32",
        )

    def test_bot_neutral_sourced_message_is_allowed(self):
        self.assertIsNone(
            assert_bot_content_allowed("Status do sistema: tudo operacional.", has_source=True)
        )


# ----------------------------------------------------------
# Official links (tests 16, 17)
# ----------------------------------------------------------
class OfficialLinkTests(unittest.TestCase):
    def test_16_official_link_validated_by_hostname(self):
        for url in ["https://stocknewsbr.com", "https://www.stocknewsbr.com/post/1"]:
            with self.subTest(url=url):
                self.assertTrue(is_official_link(url))

    def test_17_misleading_substring_and_subdomain_blocked(self):
        for url in [
            "https://stocknewsbr.com.fake.com",
            "https://fake.com/stocknewsbr.com",
            "https://stocknewsbr.com.evil.io/login",
            "http://stocknewsbr-com.attacker.net",
            "https://xn--stocknewsbr-evil.com",
            "stocknewsbr.com.fake.com",
        ]:
            with self.subTest(url=url):
                self.assertFalse(is_official_link(url))

    def test_dangerous_or_missing_url_schemes_are_blocked(self):
        for url in [
            "javascript://stocknewsbr.com/%0Aalert(1)",
            "data://stocknewsbr.com/plain,hi",
            "file://stocknewsbr.com/etc/passwd",
            "ftp://stocknewsbr.com/file",
            "stocknewsbr.com",
            "",
        ]:
            with self.subTest(url=url):
                self.assertFalse(is_official_link(url))


# ----------------------------------------------------------
# Audit (test 18)
# ----------------------------------------------------------
class AuditTests(DbCase):
    def test_18_impersonation_attempt_is_auditable(self):
        auth_audit.record_auth_event(
            self.db, "impersonation_blocked", email="liar@example.com",
            reason="impersonation_display_name_reserved",
        )
        self.db.commit()
        # Fallback: query the table directly.
        from app.models import AuthAuditEvent
        rows = self.db.query(AuthAuditEvent).filter(
            AuthAuditEvent.event == "impersonation_blocked"
        ).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].reason, "impersonation_display_name_reserved")
        # Raw forbidden identity is not stored verbatim (email is masked/hashed).
        self.assertNotIn("liar@example.com", str(rows[0].email_masked or ""))


# ----------------------------------------------------------
# Migration presence
# ----------------------------------------------------------
class MigrationTests(unittest.TestCase):
    def test_schema_patches_add_identity_columns(self):
        for col in ("official", "role", "is_bot", "official_identity_locked"):
            self.assertIn(col, SCHEMA_PATCHES["users"], col)


# ----------------------------------------------------------
# Email-change sibling endpoint guard (31B.1 security hardening)
# ----------------------------------------------------------
class EmailChangeGuardTests(DbCase):
    def _fake_request(self):
        import types

        return types.SimpleNamespace(headers={}, client=None)

    def test_email_change_blocks_official_service_email(self):
        # A regular user cannot migrate INTO an official/bot email via the
        # sibling email-change flow (register already blocks it at sign-up).
        from fastapi import BackgroundTasks

        from app.auth import request_email_change
        from app.schemas import EmailChangeRequest

        user = _mk_user(email="trader@example.com", display_name="Trader Limpo")
        self.db.add(user)
        self.db.commit()

        for spec in (OFFICIAL_ACCOUNT, OFFICIAL_BOT):
            with self.subTest(email=spec["email"]):
                payload = EmailChangeRequest(new_email=spec["email"])
                with self.assertRaises(HTTPException) as ctx:
                    request_email_change(
                        payload=payload,
                        request=self._fake_request(),
                        background_tasks=BackgroundTasks(),
                        current_user=user,
                        db=self.db,
                    )
                self.assertEqual(ctx.exception.status_code, 400)
                self.assertEqual(ctx.exception.detail, "official_email_reserved")


# ----------------------------------------------------------
# Bootstrap seed wiring (31B.1 — runtime provisioning, fail-closed)
# ----------------------------------------------------------
class SeedWiringSmokeTests(unittest.TestCase):
    def _session_factory(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        return sessionmaker(bind=engine)

    def test_bootstrap_seed_is_wired_and_idempotent(self):
        import main

        Session = self._session_factory()
        original = main.SessionLocal
        main.SessionLocal = Session
        try:
            main._seed_official_identities_if_needed()
            main._seed_official_identities_if_needed()  # idempotent second boot
        finally:
            main.SessionLocal = original

        db = Session()
        try:
            self.assertEqual(db.query(User).filter(User.official.is_(True)).count(), 2)
        finally:
            db.close()

    def test_bootstrap_seed_fail_closed_on_conflict(self):
        import main

        Session = self._session_factory()
        setup = Session()
        setup.add(
            _mk_user(
                email=OFFICIAL_ACCOUNT["email"],
                password_hash=hash_password("attackerpass123"),
                display_name="Trader Limpo",
                official=False,
                role="user",
                is_bot=False,
                official_identity_locked=False,
            )
        )
        setup.commit()
        setup.close()

        original = main.SessionLocal
        main.SessionLocal = Session
        try:
            # Must NOT raise (fail-closed swallow) and must NOT promote.
            main._seed_official_identities_if_needed()
        finally:
            main.SessionLocal = original

        db = Session()
        try:
            row = db.query(User).filter(User.email == OFFICIAL_ACCOUNT["email"]).one()
            self.assertFalse(row.official)
            self.assertEqual(row.role, "user")
            self.assertFalse(row.is_bot)
            self.assertTrue(verify_password("attackerpass123", row.password_hash))
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
