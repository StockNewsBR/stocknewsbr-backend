"""S1 — synchronous DB calls inside async handlers are offloaded via run_in_threadpool.

`async def` endpoints run on the event loop. A blocking `db.commit()` (or any
sync ORM call) inside one stalls every concurrent connection — other requests,
the WebSocket broadcast loop, keepalive. FastAPI only auto-threadpools *sync*
`def` endpoints; an `async def` endpoint owning a sync ORM call must offload it
explicitly with `await run_in_threadpool(...)` (starlette's anyio-backed worker
pool). `asyncio.create_task(sync_call)` does NOT offload — it schedules the sync
call on the loop, which is the bug, not the fix.

These checks pin the S1 remediation: the confirmed blocking sync calls in
`routes_feed`, `routes_likes`, `routes_chat`, and `routes_media` are invoked
through the route module's `run_in_threadpool`. The spy wraps the real offload
so the handler still executes end-to-end (TestClient proves the offload composes
with the real event loop); the recorded first positional argument MUST be the
sync function that used to block the loop. If anyone reverts an offload —
`await run_in_threadpool(create_post, ...)` -> `create_post(...)` — the sync
function never appears in the recorded calls and the test fails.

Isolation mirrors tests/test_mission_31b_auth_login_session.py:SocialProtectionTests
(in-memory StaticPool engine + SessionLocal patches on the social modules +
moderation state in a tempdir) so no row reaches stocknews.db.
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "unit-test-secret-key-s1-0123456789abcdef")

from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes_chat, routes_feed, routes_likes, routes_media
from app.database import Base, get_db
from app.models import User
from app.security import create_access_token, hash_password
from app.services.auth_session_service import create_user_session
from app.social import comments as social_comments
from app.social import moderation
from app.social import posts as social_posts
from app.social import db as social_db
from app.social import likes as social_likes
from app.social import reposts as social_reposts
from starlette.concurrency import run_in_threadpool as _real_offload


def _utcnow():
    from datetime import timezone
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


def _make_offload_spy():
    """Record (func, args, kwargs) for every offloaded call while still running it."""
    calls = []

    async def _spy(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return await _real_offload(func, *args, **kwargs)

    return _spy, calls


class _FakeWebSocket:
    def __init__(self, token=None, cookie_token=None, origin=None, protocol="", messages=None):
        self.query_params = {"token": token} if token is not None else {}
        self.headers = {"sec-websocket-protocol": protocol}
        if origin is not None:
            self.headers["origin"] = origin
        self.cookies = {"s": cookie_token} if cookie_token is not None else {}
        self.closed_with = None
        self.sent = []
        self._messages = list(messages) if messages else []

    async def close(self, code=None):
        self.closed_with = code

    async def send_json(self, data):
        self.sent.append(data)

    async def receive_json(self):
        if self._messages:
            return self._messages.pop(0)
        raise WebSocketDisconnect


# ---------------------------------------------------------------------------
# routes_feed + routes_likes: sync social-DB calls offloaded in async handlers.
# ---------------------------------------------------------------------------
class FeedLikesDboffloadTests(unittest.TestCase):
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
        self.addCleanup(self.tempdir.cleanup)
        self._original_moderation_path = moderation.MODERATION_STORE_PATH
        moderation.MODERATION_STORE_PATH = Path(self.tempdir.name) / "moderation_state.json"
        self.addCleanup(setattr, moderation, "MODERATION_STORE_PATH", self._original_moderation_path)

        self._patched = []
        for module in (social_posts, social_comments, social_likes, social_reposts):
            self._patched.append((module, module.SessionLocal))
            module.SessionLocal = self.SessionLocal
        self._original_initialized = social_db._initialized
        social_db._initialized = True

        def _restore():
            for module, original in self._patched:
                module.SessionLocal = original
            social_db._initialized = self._original_initialized
            self.db.close()
            Base.metadata.drop_all(bind=self.engine)
            self.engine.dispose()

        self.addCleanup(_restore)

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
        self.client = TestClient(app, raise_server_exceptions=False)

    def _bearer(self, email="social@example.com"):
        user = _make_user(self.db, email)
        session = create_user_session(self.db, user, channel="web")
        self.db.commit()
        token = create_access_token({"sub": str(user.id), "sid": session.session_id})
        return user, {"Authorization": f"Bearer {token}", "Origin": self.ORIGIN}

    def _post(self, headers, text="Analise tecnica do papel segue construtiva."):
        return self.client.post("/ticker/PETR4/post", json={"text": text}, headers=headers)

    def test_create_ticker_post_offloads_create_post(self):
        _, headers = self._bearer("poster@example.com")
        spy, calls = _make_offload_spy()
        with patch.object(routes_feed, "run_in_threadpool", spy):
            response = self._post(headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(
            any(c[0] is routes_feed.create_post for c in calls),
            "create_post must be offloaded via run_in_threadpool",
        )

    def test_create_post_comment_offloads_get_post_and_add_comment(self):
        _, headers = self._bearer("author@example.com")
        created = self._post(headers)
        post_id = created.json()["id"]

        spy, calls = _make_offload_spy()
        with patch.object(routes_feed, "run_in_threadpool", spy):
            response = self.client.post(
                f"/post/{post_id}/comment",
                json={"text": "concordo com a leitura"},
                headers=headers,
            )
        self.assertEqual(response.status_code, 200, response.text)
        funcs = {c[0] for c in calls}
        self.assertIn(routes_feed.get_post, funcs)
        self.assertIn(routes_feed.add_comment, funcs)

    def test_repost_post_offloads_create_repost(self):
        _, headers = self._bearer("reposter@example.com")
        created = self._post(headers)
        post_id = created.json()["id"]

        spy, calls = _make_offload_spy()
        with patch.object(routes_feed, "run_in_threadpool", spy):
            response = self.client.post(f"/post/{post_id}/repost", json={}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(
            any(c[0] is routes_feed.create_repost for c in calls),
            "create_repost must be offloaded via run_in_threadpool",
        )

    def test_unrepost_post_offloads_delete_repost(self):
        _, headers = self._bearer("unreposter@example.com")
        created = self._post(headers)
        post_id = created.json()["id"]
        self.client.post(f"/post/{post_id}/repost", json={}, headers=headers)

        spy, calls = _make_offload_spy()
        with patch.object(routes_feed, "run_in_threadpool", spy):
            response = self.client.delete(f"/post/{post_id}/repost", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        funcs = {c[0] for c in calls}
        self.assertIn(routes_feed.delete_repost, funcs)

    def test_delete_ticker_post_offloads_delete_post(self):
        _, headers = self._bearer("deleter@example.com")
        created = self._post(headers)
        post_id = created.json()["id"]

        spy, calls = _make_offload_spy()
        with patch.object(routes_feed, "run_in_threadpool", spy):
            response = self.client.delete(f"/post/{post_id}", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        funcs = {c[0] for c in calls}
        self.assertIn(routes_feed.get_post, funcs)
        self.assertIn(routes_feed.delete_post, funcs)

    def test_like_endpoint_offloads_like_post(self):
        _, headers = self._bearer("liker@example.com")
        created = self._post(headers)
        post_id = created.json()["id"]

        spy, calls = _make_offload_spy()
        with patch.object(routes_likes, "run_in_threadpool", spy):
            response = self.client.post(f"/post/{post_id}/like", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        funcs = {c[0] for c in calls}
        self.assertIn(routes_likes.get_post, funcs)
        self.assertIn(routes_likes.like_post, funcs)

    def test_unlike_endpoint_offloads_unlike_post(self):
        _, headers = self._bearer("unliker@example.com")
        created = self._post(headers)
        post_id = created.json()["id"]
        self.client.post(f"/post/{post_id}/like", headers=headers)

        spy, calls = _make_offload_spy()
        with patch.object(routes_likes, "run_in_threadpool", spy):
            response = self.client.post(f"/post/{post_id}/unlike", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        funcs = {c[0] for c in calls}
        self.assertIn(routes_likes.get_post, funcs)
        self.assertIn(routes_likes.unlike_post, funcs)


# ---------------------------------------------------------------------------
# routes_chat: _resolve_user_from_token offloaded in the websocket handshake.
# ---------------------------------------------------------------------------
class ChatResolveOffloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_websocket_chat_offloads_resolve_user_from_token(self):
        fake_user = {"id": 1, "display_name": "Trader"}

        spy, calls = _make_offload_spy()
        with patch.object(routes_chat, "_resolve_user_from_token", return_value=fake_user) as resolve, \
             patch.object(routes_chat, "run_in_threadpool", spy), \
             patch.object(routes_chat, "canonical_symbol", lambda s: s), \
             patch.object(routes_chat, "list_room_messages", lambda symbol, limit=60: []):
            from unittest.mock import MagicMock, AsyncMock
            manager = MagicMock()
            manager.connect = AsyncMock()
            manager.disconnect = MagicMock()
            with patch.object(routes_chat, "room_ws_manager", manager):
                ws = _FakeWebSocket(token="anything")
                await routes_chat.websocket_chat(ws, "PETR4")

        # The handler must have offloaded _resolve_user_from_token, not called
        # it inline on the event loop.
        self.assertTrue(
            any(c[0] is resolve for c in calls),
            "_resolve_user_from_token must be offloaded via run_in_threadpool",
        )
        resolve.assert_called_once_with("anything")

    async def test_websocket_chat_receive_loop_offloads_append_room_message(self):
        # The receive loop runs append_room_message (blocking file I/O +
        # interprocess lock + moderation audit) on every inbound message.
        # It must be offloaded, else one room's append stalls every concurrent
        # websocket receive and every HTTP request sharing the event loop.
        from unittest.mock import MagicMock, AsyncMock

        fake_item = {
            "id": "PETR4-abc", "symbol": "PETR4", "user_id": 1,
            "user_name": "Trader", "text": "hello", "created_at": 123,
            "status": "published",
        }
        spy, calls = _make_offload_spy()
        with patch.object(routes_chat, "_resolve_user_from_token", return_value={"id": 1, "display_name": "Trader"}), \
             patch.object(routes_chat, "append_room_message", return_value=fake_item) as amock, \
             patch.object(routes_chat, "run_in_threadpool", spy), \
             patch.object(routes_chat, "canonical_symbol", lambda s: s), \
             patch.object(routes_chat, "list_room_messages", lambda symbol, limit=60: []):
            manager = MagicMock()
            manager.connect = AsyncMock()
            manager.disconnect = MagicMock()
            manager.broadcast = AsyncMock()
            with patch.object(routes_chat, "room_ws_manager", manager):
                ws = _FakeWebSocket(
                    token="anything",
                    messages=[{"type": "message", "text": "hello"}],
                )
                await routes_chat.websocket_chat(ws, "PETR4")

        funcs = {c[0] for c in calls}
        self.assertIn(
            amock,
            funcs,
            "append_room_message must be offloaded via run_in_threadpool in the receive loop",
        )


# ---------------------------------------------------------------------------
# routes_media: RLS context + asset insert offloaded in async media_upload.
# ---------------------------------------------------------------------------
class MediaUploadOffloadTests(unittest.TestCase):
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

        app = FastAPI()
        app.include_router(routes_media.router)

        def override_get_db():
            session = self.SessionLocal()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db

        self.fake_user = SimpleNamespace(
            id=1, display_name="Trader", email="t@e.com", role="user"
        )
        from app.dependencies import require_active_plan
        app.dependency_overrides[require_active_plan] = lambda: self.fake_user
        self.addCleanup(app.dependency_overrides.clear)

        self.app = app
        self.client = TestClient(app)
        self.addCleanup(self.engine.dispose)

    def test_media_upload_offloads_rls_context_and_asset_insert(self):
        # The handler imports _apply_media_rls_context / create_media_asset at
        # module scope, so patch.object swaps those module attributes for mocks
        # that the handler then hands to run_in_threadpool. Asserting against
        # the mocks (not the originals) is what proves the offload happened.
        fake_payload = {
            "provider": "local",
            "folder": "posts",
            "filename": "chart.png",
            "content_type": "image/png",
            "size_bytes": 42,
            "url": "/media/posts/chart.png",
        }

        async def _fake_save_upload(file, folder="posts"):
            return fake_payload

        spy, calls = _make_offload_spy()
        with patch.object(routes_media, "save_upload", _fake_save_upload), \
             patch.object(routes_media, "run_in_threadpool", spy), \
             patch.object(routes_media, "_apply_media_rls_context") as rls_mock, \
             patch.object(routes_media, "create_media_asset") as asset_mock:
            asset_mock.return_value = SimpleNamespace(
                id=1, owner_user_id=1, provider="local", folder="posts",
                filename="chart.png", storage_key="posts/chart.png",
                content_type="image/png", size_bytes=42,
                public_url="/media/posts/chart.png", status="uploaded",
            )
            with patch.object(routes_media, "serialize_media_asset", lambda a: {"id": a.id}):
                response = self.client.post(
                    "/api/media/upload",
                    files={"file": ("chart.png", b"\x89PNG\r\n\x1a\n", "image/png")},
                )

        self.assertEqual(response.status_code, 200, response.text)
        funcs = {c[0] for c in calls}
        # Both the RLS context binding and the asset insert run under
        # run_in_threadpool, never inline on the event loop.
        self.assertIn(rls_mock, funcs)
        self.assertIn(asset_mock, funcs)


# ---------------------------------------------------------------------------
# routes_chat: HTTP /chat/{symbol}/message offloads append_room_message.
# ---------------------------------------------------------------------------
class ChatMessageOffloadTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(routes_chat.router)

        self.fake_user = SimpleNamespace(
            id=1, display_name="Trader", email="t@e.com", role="user"
        )
        from app.dependencies import require_active_plan
        app.dependency_overrides[require_active_plan] = lambda: self.fake_user
        self.addCleanup(app.dependency_overrides.clear)

        self.client = TestClient(app)

    def test_chat_message_http_offloads_append_room_message(self):
        from unittest.mock import AsyncMock

        # append_room_message does blocking file I/O + interprocess lock +
        # moderation audit. In the async HTTP handler it must be offloaded.
        fake_item = {
            "id": "PETR4-abc", "symbol": "PETR4", "user_id": 1,
            "user_name": "Trader", "text": "hello", "created_at": 123,
            "status": "published",
        }
        spy, calls = _make_offload_spy()
        with patch.object(routes_chat, "append_room_message", return_value=fake_item) as amock, \
             patch.object(routes_chat, "run_in_threadpool", spy), \
             patch.object(routes_chat, "canonical_symbol", lambda s: s), \
             patch.object(routes_chat, "room_ws_manager") as mgr:
            mgr.broadcast = AsyncMock()
            response = self.client.post("/chat/PETR4/message", json={"text": "hello"})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(
            any(c[0] is amock for c in calls),
            "append_room_message must be offloaded via run_in_threadpool",
        )


if __name__ == "__main__":
    unittest.main()
