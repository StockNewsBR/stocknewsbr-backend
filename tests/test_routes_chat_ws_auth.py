"""B1/B3 — WebSocket auth: fail closed, never silent, never logged token.

`_resolve_user_from_token` used to swallow every failure in a silent
`except Exception: return None` and also called `refresh_user_access`
twice (once explicitly, once inside `has_channel_access`). After B1/B3:

* expected denials (`HTTPException` from `resolve_token_user`/token decode
  — bad/expired token, unknown/revoked/expired session, unknown user) return
  None without a noisy stack trace;
* unexpected failures (DB down, access/refresh crash) still return None
  (fail closed) but are logged via `logger.exception` so they cannot vanish;
* the log message and traceback never carry the token, Authorization header,
  or any secret/credential;
* the DB session is closed on every path (success, expected, unexpected);
* refresh happens exactly once, inside `has_channel_access`;
* the public contract (`{"id","display_name"}` or None) and the WebSocket
  close code `WS_1008_POLICY_VIOLATION` on denial are preserved.

Real-token tests bind `routes_chat.SessionLocal` to a private in-memory
SQLite engine (mirroring tests/test_mission_31b_auth_login_session.py) so
no row ever reaches the working stocknews.db.
"""

import os
import unittest
from datetime import timedelta

os.environ.setdefault("SECRET_KEY", "unit-test-secret-key-b1b3-0123456789abcdef")
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import WebSocketDisconnect, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes_chat
from app.database import Base
from app.models import User
from app.security import create_access_token, hash_password
from app.services import access_service
from app.services.auth_session_service import create_user_session

def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_user(db, email="trader@example.com", plan="trial"):
    now = _utcnow()
    user = User(
        email=email,
        password_hash=hash_password("123456"),
        display_name="Trader",
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


class _FakeWebSocket:
    """Minimal stand-in for the WebSocket surface websocket_chat touches."""

    def __init__(self, token=None, cookie_token=None, origin=None, protocol=""):
        self.query_params = {"token": token} if token is not None else {}
        self.headers = {"sec-websocket-protocol": protocol}
        if origin is not None:
            self.headers["origin"] = origin
        self.cookies = {"s": cookie_token} if cookie_token is not None else {}
        self.closed_with = None
        self.sent = []

    async def close(self, code=None):
        self.closed_with = code

    async def send_json(self, data):
        self.sent.append(data)

    async def receive_json(self):
        raise WebSocketDisconnect


# ---------------------------------------------------------------------------
# Real token flow against a private in-memory engine.
# ---------------------------------------------------------------------------
class ChatTokenResolveRealDbTests(unittest.TestCase):
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
        self._patch(patch.object(routes_chat, "SessionLocal", self.SessionLocal))

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _patch(self, patcher):
        patcher.start()
        self.addCleanup(patcher.stop)

    def _seed_token(self, email="trader@example.com"):
        user = _make_user(self.db, email=email)
        session = create_user_session(self.db, user, channel="app")
        self.db.commit()
        token = create_access_token({"sub": str(user.id), "sid": session.session_id})
        return user, session, token

    def test_valid_token_resolves_user_and_preserves_contract(self):
        user, _session, token = self._seed_token()

        resolved = routes_chat._resolve_user_from_token(token)

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["id"], user.id)
        self.assertIn("display_name", resolved)
        self.assertNotIn("token", resolved)
        self.assertNotIn("password", resolved)

    def test_garbage_token_returns_none(self):
        self.assertIsNone(routes_chat._resolve_user_from_token("not-a-jwt"))

    def test_unknown_session_sid_returns_none(self):
        user, _session, _token = self._seed_token()
        token = create_access_token({"sub": str(user.id), "sid": "unknown-session-sid"})

        self.assertIsNone(routes_chat._resolve_user_from_token(token))

    def test_expired_session_returns_none(self):
        user, session, _token = self._seed_token(email="expire@example.com")
        session.expires_at = _utcnow() - timedelta(seconds=1)
        self.db.commit()
        token = create_access_token({"sub": str(user.id), "sid": session.session_id})

        self.assertIsNone(routes_chat._resolve_user_from_token(token))

    def test_unknown_user_returns_none(self):
        _user, session, _token = self._seed_token(email="ghost@example.com")
        # Valid signature + a live session id, but the subject names a
        # user that does not exist -> resolve_token_user raises before the
        # session lookup.
        token = create_access_token({"sub": "999999", "sid": session.session_id})

        self.assertIsNone(routes_chat._resolve_user_from_token(token))

    def test_refresh_user_access_called_exactly_once(self):
        # CASO A: has_channel_access already calls refresh_user_access, so the
        # explicit call that used to live in _resolve_user_from_token was a
        # redundant second refresh. Removing it leaves exactly one.
        _user, _session, token = self._seed_token(email="once@example.com")

        with patch.object(
            access_service,
            "refresh_user_access",
            wraps=access_service.refresh_user_access,
        ) as refresh_spy:
            resolved = routes_chat._resolve_user_from_token(token)

        self.assertIsNotNone(resolved)
        self.assertEqual(refresh_spy.call_count, 1)


# ---------------------------------------------------------------------------
# Session closure + logging behavior (no real DB needed).
# ---------------------------------------------------------------------------
class ChatSessionAndLoggingTests(unittest.TestCase):
    def _fake_user(self):
        return SimpleNamespace(id=1, is_active=True, display_name="Trader", email="t@e.com")

    def _patch_resolve(self, side_effect=None, return_value=None):
        if side_effect is not None:
            return patch.object(routes_chat, "resolve_token_user", side_effect=side_effect)
        return patch.object(routes_chat, "resolve_token_user", return_value=return_value)

    def test_session_closed_on_success(self):
        db_mock = MagicMock()
        with patch.object(routes_chat, "SessionLocal", lambda: db_mock), patch.object(
            routes_chat, "resolve_token_user", return_value=self._fake_user()
        ), patch.object(routes_chat, "has_channel_access", return_value=True):
            resolved = routes_chat._resolve_user_from_token("ok")

        self.assertEqual(resolved["id"], 1)
        db_mock.close.assert_called_once()

    def test_session_closed_on_auth_failure_without_logging(self):
        from fastapi import HTTPException

        db_mock = MagicMock()
        with patch.object(routes_chat, "SessionLocal", lambda: db_mock), patch.object(
            routes_chat, "resolve_token_user", side_effect=HTTPException(status_code=401)
        ):
            with self.assertNoLogs("app.api.routes_chat", level="ERROR"):
                resolved = routes_chat._resolve_user_from_token("bad")

        self.assertIsNone(resolved)
        db_mock.close.assert_called_once()

    def test_session_closed_on_db_failure_and_logged(self):
        db_mock = MagicMock()
        with patch.object(routes_chat, "SessionLocal", lambda: db_mock), patch.object(
            routes_chat, "resolve_token_user", side_effect=RuntimeError("db unavailable")
        ):
            with self.assertLogs("app.api.routes_chat", level="ERROR") as cm:
                resolved = routes_chat._resolve_user_from_token("bad")

        self.assertIsNone(resolved)
        self.assertEqual(len(cm.records), 1)
        db_mock.close.assert_called_once()

    def test_session_closed_on_unexpected_exception_and_logged(self):
        db_mock = MagicMock()
        with patch.object(routes_chat, "SessionLocal", lambda: db_mock), patch.object(
            routes_chat, "resolve_token_user", return_value=self._fake_user()
        ), patch.object(routes_chat, "has_channel_access", side_effect=RuntimeError("boom")):
            with self.assertLogs("app.api.routes_chat", level="ERROR") as cm:
                resolved = routes_chat._resolve_user_from_token("bad")

        self.assertIsNone(resolved)
        self.assertEqual(len(cm.records), 1)
        db_mock.close.assert_called_once()

    def test_token_value_absent_from_error_logs(self):
        sentinel = "SECRETSENTINEL-DO-NOT-LOG"
        db_mock = MagicMock()
        with patch.object(routes_chat, "SessionLocal", lambda: db_mock), patch.object(
            routes_chat, "resolve_token_user", side_effect=RuntimeError("boom")
        ):
            with self.assertLogs("app.api.routes_chat", level="ERROR") as cm:
                resolved = routes_chat._resolve_user_from_token(sentinel)

        self.assertIsNone(resolved)
        for line in cm.output:
            self.assertNotIn(sentinel, line)


# ---------------------------------------------------------------------------
# WebSocket deny / accept flows.
# ---------------------------------------------------------------------------
class WebSocketDenyFlowTests(unittest.IsolatedAsyncioTestCase):
    def _patch(self, module, attr, new=None, **kwargs):
        if new is not None:
            kwargs["new"] = new
        patcher = patch.object(module, attr, **kwargs)
        patcher.start()
        self.addCleanup(patcher.stop)
        return patcher

    async def test_ws_denied_on_refresh_failure_closes_1008(self):
        db_mock = MagicMock()
        self._patch(routes_chat, "SessionLocal", lambda: db_mock)
        self._patch(routes_chat, "resolve_token_user", return_value=SimpleNamespace(
            id=1, is_active=True, display_name="Trader", email="t@e.com"
        ))
        self._patch(routes_chat, "has_channel_access", side_effect=RuntimeError("refresh broke"))
        self._patch(routes_chat, "canonical_symbol", lambda s: s)
        manager = MagicMock()
        manager.connect = AsyncMock()
        self._patch(routes_chat, "room_ws_manager", manager)

        ws = _FakeWebSocket(token="whatever")
        with self.assertLogs("app.api.routes_chat", level="ERROR"):
            await routes_chat.websocket_chat(ws, "PETR4")

        self.assertEqual(ws.closed_with, status.WS_1008_POLICY_VIOLATION)
        manager.connect.assert_not_awaited()

    async def test_ws_denied_on_missing_token_closes_1008(self):
        self._patch(routes_chat, "canonical_symbol", lambda s: s)
        self._patch(routes_chat, "session_cookie_name", lambda: "s")

        ws = _FakeWebSocket(token=None, cookie_token=None)
        await routes_chat.websocket_chat(ws, "PETR4")

        self.assertEqual(ws.closed_with, status.WS_1008_POLICY_VIOLATION)

    async def test_ws_origin_guard_rejects_cross_site_cookie_closes_1008(self):
        self._patch(routes_chat, "canonical_symbol", lambda s: s)
        self._patch(routes_chat, "session_cookie_name", lambda: "s")
        self._patch(routes_chat, "_cookie_websocket_origin_allowed", return_value=False)

        ws = _FakeWebSocket(token=None, cookie_token="stolen-cookie", origin="https://evil.example")
        await routes_chat.websocket_chat(ws, "PETR4")

        self.assertEqual(ws.closed_with, status.WS_1008_POLICY_VIOLATION)

    async def test_ws_valid_token_connects_and_sends_history(self):
        self._patch(routes_chat, "canonical_symbol", lambda s: s)
        self._patch(routes_chat, "_resolve_user_from_token", return_value={
            "id": 1, "display_name": "Trader"
        })
        self._patch(routes_chat, "list_room_messages", lambda symbol, limit=60: [{"hi": 1}])

        manager = MagicMock()
        manager.connect = AsyncMock()
        manager.disconnect = MagicMock()
        self._patch(routes_chat, "room_ws_manager", manager)

        ws = _FakeWebSocket(token="ok")
        await routes_chat.websocket_chat(ws, "PETR4")

        self.assertIsNone(ws.closed_with)
        manager.connect.assert_awaited_once()
        self.assertTrue(any(m.get("type") == "history" for m in ws.sent))
        manager.disconnect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
