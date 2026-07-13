import asyncio
import inspect
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, WebSocketDisconnect, status
from fastapi.testclient import TestClient

from app.api import routes_chat
from app.Frontend.trader_terminal import get_terminal
from app.security import get_request_token
from app.web import routes_terminal


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class _ScriptCounter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.script_starts = 0

    def handle_starttag(self, tag, attrs):
        del attrs
        if tag.lower() == "script":
            self.script_starts += 1


class _FakeWebSocket:
    def __init__(self, *, cookies=None, headers=None, query_params=None):
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.query_params = query_params or {}
        self.closed_code = None
        self.sent = []

    async def close(self, code):
        self.closed_code = code

    async def send_json(self, payload):
        self.sent.append(payload)

    async def receive_json(self):
        raise WebSocketDisconnect()


def test_terminal_inline_script_data_cannot_create_an_extra_script_element():
    payload = "</script><script>window.__snbr_xss_probe=31337</script>"
    renderer_parameters = inspect.signature(get_terminal).parameters
    render_kwargs = {"focused_tab": payload}

    if "token" in renderer_parameters:
        render_kwargs["token"] = payload

    html = get_terminal(**render_kwargs)
    parser = _ScriptCounter()
    parser.feed(html)

    assert parser.script_starts == 1
    assert payload not in html


def test_terminal_route_ignores_legacy_query_payload_without_reflecting_it():
    app = FastAPI()
    app.include_router(routes_terminal.router)

    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        for dependency in dependant.dependencies:
            if getattr(dependency.call, "__name__", "") == "_dependency":
                app.dependency_overrides[dependency.call] = lambda: object()

    payload = "</script><script>window.__snbr_xss_probe=31337</script>"
    response = TestClient(app).get(
        "/web/terminal/ui",
        params={"token": payload},
    )
    parser = _ScriptCounter()
    parser.feed(response.text)

    assert response.status_code == 200
    assert payload not in response.text
    assert parser.script_starts == 1


def test_terminal_routes_and_renderer_do_not_accept_query_bearer_parameters():
    assert "token" not in inspect.signature(get_terminal).parameters
    assert "token" not in inspect.signature(routes_terminal.terminal_ui).parameters
    assert "token" not in inspect.signature(routes_terminal.terminal_popout).parameters


def test_browser_sources_do_not_transport_bearer_tokens_in_urls():
    source_paths = [
        REPOSITORY_ROOT / "app" / "Frontend" / "trader_terminal.py",
        REPOSITORY_ROOT / "app" / "api" / "routes_chat.py",
        REPOSITORY_ROOT / "apps" / "web" / "components" / "workspace-shell.tsx",
    ]
    forbidden_fragments = (
        'searchParams.get("token")',
        'query_params.get("token")',
        "?token=${",
        "&token=${",
        "access_token=",
        "bearer=",
        "AUTH_TOKEN",
    )

    for source_path in source_paths:
        source = source_path.read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            assert fragment not in source, f"{fragment!r} remains in {source_path}"


def test_cookie_authenticated_terminal_keeps_popout_and_websocket_paths():
    html = get_terminal()
    workspace_source = (
        REPOSITORY_ROOT / "apps" / "web" / "components" / "workspace-shell.tsx"
    ).read_text(encoding="utf-8")

    assert "/web/workspace/data" in html
    assert "/web/terminal/popout/" in html
    assert "/ws/chat/" in html
    assert "new WebSocket" in html
    assert "credentials: \"include\"" in (
        REPOSITORY_ROOT / "apps" / "web" / "lib" / "api.ts"
    ).read_text(encoding="utf-8")
    assert "buildWebSocketUrl(`/ws/chat/" in workspace_source


def test_http_token_extraction_ignores_query_and_preserves_header_and_cookie():
    query_only_request = SimpleNamespace(
        cookies={},
        query_params={"token": "legacy-query-bearer"},
    )
    cookie_request = SimpleNamespace(
        cookies={"snb_session": "cookie-bearer"},
        query_params={},
    )

    assert get_request_token(query_only_request, None) is None
    assert get_request_token(query_only_request, "header-bearer") == "header-bearer"

    with patch("app.security.session_cookie_name", return_value="snb_session"):
        assert get_request_token(cookie_request, None) == "cookie-bearer"


def test_websocket_rejects_legacy_query_bearer_without_cookie_or_header():
    websocket = _FakeWebSocket(query_params={"token": "legacy-query-bearer"})

    with patch.object(routes_chat, "_resolve_user_from_token", return_value=None) as resolver:
        asyncio.run(routes_chat.websocket_chat(websocket, "PETR4"))

    assert websocket.closed_code == status.WS_1008_POLICY_VIOLATION
    resolver.assert_called_once_with(None)


def test_websocket_preserves_non_browser_authorization_header():
    websocket = _FakeWebSocket(headers={"authorization": "Bearer header-bearer"})
    user = {"id": 7, "display_name": "Header Client"}

    with (
        patch.object(routes_chat, "_resolve_user_from_token", return_value=user) as resolver,
        patch.object(routes_chat, "list_room_messages", return_value=[]),
        patch.object(routes_chat.room_ws_manager, "connect", new=AsyncMock()) as connect,
        patch.object(routes_chat.room_ws_manager, "disconnect") as disconnect,
    ):
        asyncio.run(routes_chat.websocket_chat(websocket, "PETR4"))

    assert websocket.closed_code is None
    assert websocket.sent[0]["type"] == "history"
    resolver.assert_called_once_with("header-bearer")
    connect.assert_awaited_once()
    disconnect.assert_called_once()


def test_websocket_preserves_cookie_authentication_with_allowed_origin():
    websocket = _FakeWebSocket(
        cookies={"snb_session": "cookie-bearer"},
        headers={"origin": "http://localhost:3000"},
    )
    user = {"id": 8, "display_name": "Cookie Client"}

    with (
        patch.object(routes_chat, "session_cookie_name", return_value="snb_session"),
        patch.object(routes_chat, "_cookie_websocket_origin_allowed", return_value=True),
        patch.object(routes_chat, "_resolve_user_from_token", return_value=user) as resolver,
        patch.object(routes_chat, "list_room_messages", return_value=[]),
        patch.object(routes_chat.room_ws_manager, "connect", new=AsyncMock()),
        patch.object(routes_chat.room_ws_manager, "disconnect"),
    ):
        asyncio.run(routes_chat.websocket_chat(websocket, "PETR4"))

    assert websocket.closed_code is None
    assert websocket.sent[0]["type"] == "history"
    resolver.assert_called_once_with("cookie-bearer")


# =====================================================================
# Additional Mission 35FIX findings (continuation): upload streaming,
# report uniqueness, login CSRF, news cache-only, bounded warmup.
# =====================================================================


class _FakeUpload:
    """Minimal async UploadFile stand-in that records read() sizes."""

    def __init__(self, data: bytes, content_type: str = "image/png"):
        import io

        self._buffer = io.BytesIO(data)
        self.content_type = content_type
        self.read_sizes = []

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if size is None or size < 0:
            return self._buffer.read()
        return self._buffer.read(size)


def test_media_upload_rejects_oversize_without_full_read(tmp_path):
    import pytest
    from fastapi import HTTPException

    from app.services import media_service

    root = tmp_path / "media"
    with (
        patch.object(media_service, "MEDIA_ROOT", root),
        patch.object(media_service, "MEDIA_MAX_MB", 1),
        patch.object(media_service, "increment_uploads", lambda: None),
    ):
        oversized = b"x" * (2 * 1024 * 1024 + 7)
        upload = _FakeUpload(oversized)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(media_service.save_upload(upload, folder="posts"))

        assert exc_info.value.status_code == 413
        # Streamed in bounded chunks — never a single unbounded read().
        assert upload.read_sizes
        assert all(size and size > 0 for size in upload.read_sizes)
        assert max(upload.read_sizes) <= media_service.UPLOAD_CHUNK_SIZE
        # No final asset and no partial temp file left behind.
        posts_dir = root / "posts"
        leftovers = list(posts_dir.glob("*")) if posts_dir.exists() else []
        assert leftovers == []


def test_media_upload_accepts_valid_file(tmp_path):
    from app.services import media_service

    root = tmp_path / "media"
    with (
        patch.object(media_service, "MEDIA_ROOT", root),
        patch.object(media_service, "MEDIA_MAX_MB", 1),
        patch.object(media_service, "increment_uploads", lambda: None),
    ):
        payload = b"y" * 4096
        upload = _FakeUpload(payload)
        result = asyncio.run(media_service.save_upload(upload, folder="posts"))

        assert result["size_bytes"] == len(payload)
        final_path = root / "posts" / result["filename"]
        assert final_path.read_bytes() == payload
        siblings = [p for p in (root / "posts").glob("*") if p.name != result["filename"]]
        assert siblings == []


def test_repeated_reports_by_same_user_do_not_auto_hide(tmp_path):
    from app.social import moderation

    store = tmp_path / "moderation_state.json"
    with (
        patch.object(moderation, "MODERATION_STORE_PATH", store),
        patch.object(moderation, "REPORT_THRESHOLD_AUTO_HIDE", 4),
        patch.object(moderation, "increment_reports", lambda: None),
    ):
        for _ in range(6):
            moderation.report(user_id=101, post_id=555, reason="spam", target_user_id=999)

        assert moderation.is_post_hidden(555) is False
        queue = {item["post_id"]: item for item in moderation.get_review_queue()}
        assert queue[555]["reports"] == 1


def test_distinct_reporters_reach_auto_hide(tmp_path):
    from app.social import moderation

    store = tmp_path / "moderation_state.json"
    with (
        patch.object(moderation, "MODERATION_STORE_PATH", store),
        patch.object(moderation, "REPORT_THRESHOLD_AUTO_HIDE", 4),
        patch.object(moderation, "increment_reports", lambda: None),
    ):
        for reporter in (1, 2, 3, 4):
            moderation.report(user_id=reporter, post_id=777, reason="spam", target_user_id=999)

        assert moderation.is_post_hidden(777) is True


def test_session_establishment_rejects_foreign_origin():
    import pytest
    from fastapi import HTTPException

    from app.core import csrf

    request = SimpleNamespace(headers={"origin": "https://attacker.example.com"})
    with pytest.raises(HTTPException) as exc_info:
        csrf.enforce_session_establishment_origin(request)
    assert exc_info.value.status_code == 403


def test_session_establishment_allows_same_origin_and_dev_no_origin():
    from app.core import csrf

    # An allowlisted browser origin is accepted in any environment.
    allowed = csrf.allowed_web_origins()[0]
    csrf.enforce_session_establishment_origin(SimpleNamespace(headers={"origin": allowed}))
    # Absent Origin/Referer is allowed in dev/test (the test client sends
    # neither); production is handled by the fail-closed test below.
    with patch.object(csrf, "_current_env_normalized", return_value="development"):
        csrf.enforce_session_establishment_origin(SimpleNamespace(headers={}))


def test_session_establishment_fails_closed_without_origin_in_production():
    import pytest
    from fastapi import HTTPException

    from app.core import csrf

    with patch.object(csrf, "_current_env_normalized", return_value="production"):
        with pytest.raises(HTTPException) as exc_info:
            csrf.enforce_session_establishment_origin(SimpleNamespace(headers={}))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == csrf.SESSION_ORIGIN_MISSING_DETAIL


def test_session_establishment_guard_is_web_channel_only():
    # Client separation is by channel: _issue_session only invokes the guard
    # for the web (cookie) channel, so mobile/API ("app" channel, bearer) logins
    # never reach it and never receive a web cookie.
    import inspect

    from app import auth

    source = inspect.getsource(auth._issue_session)
    guard_line = next(
        line for line in source.splitlines() if "enforce_session_establishment_origin" in line
    )
    # The guard call sits under a `normalized_channel == "web"` branch.
    assert 'normalized_channel == "web"' in source
    assert guard_line.startswith("        ")  # indented under the web-only branch


def test_news_route_never_fetches_synchronously_on_refresh():
    from app.api import routes_news

    captured = {}

    def fake_build(symbol, **kwargs):
        captured.update(kwargs)
        return {"symbol": symbol, "cache_only": not kwargs.get("allow_fetch")}

    with patch.object(routes_news, "build_public_news_payload", side_effect=fake_build):
        routes_news.symbol_news(
            symbol="AAPL", limit=6, refresh="1", current_user=SimpleNamespace(id=1)
        )

    assert captured["allow_fetch"] is False
    assert captured["schedule_warmup"] is True


def test_warmup_is_bounded_and_overflow_is_dropped():
    from threading import BoundedSemaphore

    from app.system import news_warmup

    submitted = []

    with (
        patch.object(news_warmup, "_async_slots", BoundedSemaphore(2)),
        patch.object(
            news_warmup._async_executor,
            "submit",
            side_effect=lambda *a, **k: submitted.append(a),
        ),
        patch.object(news_warmup, "_read_requests", lambda: {}),
        patch.object(news_warmup, "_write_requests", lambda *a, **k: None),
        patch.object(news_warmup, "_is_on_cooldown", lambda *a, **k: False),
        patch.object(
            news_warmup, "sanitize_market_symbol", side_effect=lambda s: str(s or "").upper()
        ),
    ):
        news_warmup._async_running.clear()
        news_warmup._async_last_request_at.clear()
        try:
            for symbol in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF"):
                news_warmup.request_news_warmup(symbol)
            # Bounded: at most (workers + queue) submissions; a burst of distinct
            # cold symbols cannot spawn unlimited threads/queue growth.
            assert len(submitted) <= 2
        finally:
            news_warmup._async_running.clear()
            news_warmup._async_last_request_at.clear()


def test_terminal_main_page_is_not_a_popout():
    html = get_terminal()
    # A None focused_tab is serialized as JSON null (never coerced to "home"),
    # so IS_POPOUT = Boolean(FOCUSED_TAB) evaluates to false on the main page.
    assert "const FOCUSED_TAB = null;" in html
    assert 'const FOCUSED_TAB = "home"' not in html
    assert "const IS_POPOUT = Boolean(FOCUSED_TAB);" in html


def test_terminal_popout_preserves_explicit_focused_tab():
    html = get_terminal(focused_tab="portfolio")
    # An explicitly provided focused_tab is preserved verbatim -> IS_POPOUT true.
    assert 'const FOCUSED_TAB = "portfolio";' in html


def test_terminal_malicious_focused_tab_cannot_break_out_of_script():
    payload = "</script><script>window.__snbr_focus_probe=31337</script>"

    baseline = _ScriptCounter()
    baseline.feed(get_terminal())
    attacked = _ScriptCounter()
    attacked.feed(get_terminal(focused_tab=payload))

    # The malicious focused_tab cannot open an additional <script> element.
    assert attacked.script_starts == baseline.script_starts
    # The raw closing tag is neutralized (escaped), never emitted verbatim.
    assert "</script><script>window.__snbr_focus_probe" not in get_terminal(focused_tab=payload)


# =====================================================================
# Open structural findings: #4 upload quota, #7 WS revocation, #10 Telegram.
# =====================================================================


def _open_test_db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.models import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False)()


def _media_asset(owner_user_id, size_bytes, filename, status="uploaded"):
    from app.models import MediaAsset

    return MediaAsset(
        owner_user_id=owner_user_id,
        provider="local",
        folder="posts",
        filename=filename,
        size_bytes=size_bytes,
        status=status,
    )


def test_media_quota_accepts_at_limit_and_rejects_over_by_one_byte():
    import pytest
    from fastapi import HTTPException

    from app.services import media_service

    db = _open_test_db_session()
    db.add(_media_asset(1, 100, "a.png"))
    db.commit()

    with (
        patch.object(media_service, "media_user_quota_bytes", return_value=150),
        patch.object(media_service, "media_user_max_objects", return_value=1000),
    ):
        # Exactly at the limit (100 + 50 == 150) is accepted.
        media_service.enforce_media_quota(db, owner_user_id=1, new_bytes=50)
        # One byte over (100 + 51 == 151) is rejected.
        with pytest.raises(HTTPException) as exc:
            media_service.enforce_media_quota(db, owner_user_id=1, new_bytes=51)
    assert exc.value.status_code == 413


def test_media_quota_is_per_owner_and_freed_on_delete():
    from app.services import media_service

    db = _open_test_db_session()
    asset = _media_asset(1, 100, "a.png")
    db.add(asset)
    db.commit()

    # A different owner has an independent (empty) quota.
    assert media_service.current_media_usage(db, 2) == (0, 0)
    assert media_service.current_media_usage(db, 1) == (100, 1)

    # Deleting the row frees quota automatically (no separate release path).
    db.delete(asset)
    db.commit()
    assert media_service.current_media_usage(db, 1) == (0, 0)


def test_media_object_count_limit_is_enforced():
    import pytest
    from fastapi import HTTPException

    from app.services import media_service

    db = _open_test_db_session()
    db.add(_media_asset(1, 1, "a.png"))
    db.commit()

    with (
        patch.object(media_service, "media_user_quota_bytes", return_value=10 ** 12),
        patch.object(media_service, "media_user_max_objects", return_value=1),
    ):
        with pytest.raises(HTTPException) as exc:
            media_service.enforce_media_quota(db, owner_user_id=1, new_bytes=1)
    assert exc.value.status_code == 413


def test_media_quota_production_rejects_invalid_config():
    import os

    import pytest

    from app.services import media_service

    with (
        patch.dict(os.environ, {"MEDIA_USER_QUOTA_MB": "0"}),
        patch.object(media_service, "_current_env_normalized", return_value="production"),
    ):
        with pytest.raises(RuntimeError):
            media_service.media_user_quota_bytes()


def test_media_upload_route_enforces_quota_and_removes_rejected_file(tmp_path):
    import pytest
    from fastapi import HTTPException

    from app.api import routes_media
    from app.services import media_service

    db = _open_test_db_session()
    root = tmp_path / "media"
    user = SimpleNamespace(id=1)

    with (
        patch.object(media_service, "MEDIA_ROOT", root),
        patch.object(media_service, "MEDIA_MAX_MB", 5),
        patch.object(media_service, "increment_uploads", lambda: None),
        patch.object(media_service, "media_user_quota_bytes", return_value=1024),
        patch.object(media_service, "media_user_max_objects", return_value=100),
    ):
        first = asyncio.run(
            routes_media.media_upload(file=_FakeUpload(b"a" * 600), current_user=user, db=db)
        )
        assert first["size_bytes"] == 600

        # 600 + 600 == 1200 > 1024 -> rejected, and the streamed file removed,
        # so a rejected upload consumes neither disk nor quota.
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                routes_media.media_upload(file=_FakeUpload(b"b" * 600), current_user=user, db=db)
            )
        assert exc.value.status_code == 413

        remaining = list((root / "posts").glob("*.png"))
        assert len(remaining) == 1
        assert media_service.current_media_usage(db, 1) == (600, 1)


class _RevocableWebSocket:
    def __init__(self, messages):
        self.cookies = {"snb_session": "tok"}
        self.headers = {"origin": "https://stocknewsbr.com"}
        self.closed_code = None
        self.sent = []
        self._messages = list(messages)

    async def close(self, code):
        self.closed_code = code

    async def send_json(self, payload):
        self.sent.append(payload)

    async def receive_json(self):
        if self._messages:
            return self._messages.pop(0)
        raise WebSocketDisconnect()


def test_websocket_closes_after_session_revocation():
    from app.api import routes_chat

    ws = _RevocableWebSocket([{"type": "message", "text": "hello"}])
    calls = {"n": 0}

    def revocable_resolve(token):
        calls["n"] += 1
        # Valid at handshake, revoked by the time the first frame is processed.
        return {"id": 7, "display_name": "U"} if calls["n"] == 1 else None

    with (
        patch.object(routes_chat, "session_cookie_name", return_value="snb_session"),
        patch.object(routes_chat, "_cookie_websocket_origin_allowed", return_value=True),
        patch.object(routes_chat, "_resolve_user_from_token", side_effect=revocable_resolve),
        patch.object(routes_chat, "list_room_messages", return_value=[]),
        patch.object(routes_chat.room_ws_manager, "connect", new=AsyncMock()),
        patch.object(routes_chat.room_ws_manager, "disconnect"),
        patch.object(routes_chat, "append_room_message") as append_mock,
    ):
        asyncio.run(routes_chat.websocket_chat(ws, "PETR4"))

    assert ws.closed_code == status.WS_1008_POLICY_VIOLATION
    # A revoked session never publishes protected content.
    append_mock.assert_not_called()


def test_websocket_valid_session_keeps_publishing():
    from app.api import routes_chat

    ws = _RevocableWebSocket([{"type": "message", "text": "hi"}])

    with (
        patch.object(routes_chat, "session_cookie_name", return_value="snb_session"),
        patch.object(routes_chat, "_cookie_websocket_origin_allowed", return_value=True),
        patch.object(
            routes_chat,
            "_resolve_user_from_token",
            return_value={"id": 7, "display_name": "U"},
        ),
        patch.object(routes_chat, "list_room_messages", return_value=[]),
        patch.object(routes_chat.room_ws_manager, "connect", new=AsyncMock()),
        patch.object(routes_chat.room_ws_manager, "broadcast", new=AsyncMock()) as broadcast_mock,
        patch.object(routes_chat.room_ws_manager, "disconnect"),
        patch.object(routes_chat, "append_room_message", return_value={"id": 1, "text": "hi"}),
    ):
        asyncio.run(routes_chat.websocket_chat(ws, "PETR4"))

    assert ws.closed_code is None
    broadcast_mock.assert_awaited()


def test_telegram_direct_link_is_rejected_without_mutation():
    import pytest
    from fastapi import HTTPException

    from app import auth

    user = SimpleNamespace(id=1, telegram_id=None)
    payload = SimpleNamespace(telegram_id="999", telegram_username="attacker")

    with pytest.raises(HTTPException) as exc:
        auth.telegram_link(payload=payload, current_user=user, db=object())

    assert exc.value.status_code == 409
    assert exc.value.detail == "telegram_direct_link_disabled"
    # The client-supplied telegram_id was never bound to the account.
    assert user.telegram_id is None


# =====================================================================
# CodeRabbit final-review fixes: media path confinement, upload cleanup on
# any failure, safe WebSocket interval parsing.
# =====================================================================


def test_remove_media_file_is_confined_to_media_root(tmp_path):
    from app.services import media_service

    root = tmp_path / "media"
    (root / "posts").mkdir(parents=True)
    legit = root / "posts" / "ok.png"
    legit.write_bytes(b"x")
    outside = tmp_path / "secret.txt"
    outside.write_bytes(b"secret")

    with patch.object(media_service, "MEDIA_ROOT", root):
        # A legitimate file inside MEDIA_ROOT is removed.
        media_service.remove_media_file("posts", "ok.png")
        assert not legit.exists()

        # `..` traversal cannot delete an external file.
        media_service.remove_media_file("posts", "../../secret.txt")
        assert outside.exists()

        # An absolute filename component cannot escape the root.
        media_service.remove_media_file("", str(outside))
        assert outside.exists()

        # MEDIA_ROOT itself is never deleted, and a missing file is safe.
        media_service.remove_media_file(".", "")
        assert root.exists()
        media_service.remove_media_file("posts", "missing.png")


def test_media_upload_removes_streamed_file_on_non_http_failure(tmp_path):
    import pytest

    from app.api import routes_media
    from app.services import media_service

    db = _open_test_db_session()
    root = tmp_path / "media"
    user = SimpleNamespace(id=1)

    with (
        patch.object(media_service, "MEDIA_ROOT", root),
        patch.object(media_service, "MEDIA_MAX_MB", 5),
        patch.object(media_service, "increment_uploads", lambda: None),
        patch.object(media_service, "media_user_quota_bytes", return_value=10 ** 9),
        patch.object(media_service, "media_user_max_objects", return_value=1000),
        patch.object(routes_media, "create_media_asset", side_effect=RuntimeError("db down")),
    ):
        # A non-HTTPException persistence failure must still remove the streamed
        # file (no orphan) and re-raise the original exception unchanged.
        with pytest.raises(RuntimeError):
            asyncio.run(
                routes_media.media_upload(file=_FakeUpload(b"a" * 100), current_user=user, db=db)
            )

    assert list((root / "posts").glob("*.png")) == []


def test_chat_ws_interval_parsing_is_safe():
    import importlib
    import os

    from app.api import routes_chat

    cases = {"abc": 30, "": 30, "0": 1, "-5": 1, "45": 45}
    try:
        for value, expected in cases.items():
            with patch.dict(os.environ, {"CHAT_WS_REVALIDATE_SECONDS": value}):
                importlib.reload(routes_chat)
                assert routes_chat.CHAT_WS_REVALIDATE_SECONDS == expected, value
        # A missing variable falls back to the safe default without crashing.
        env_without = {k: v for k, v in os.environ.items() if k != "CHAT_WS_REVALIDATE_SECONDS"}
        with patch.dict(os.environ, env_without, clear=True):
            importlib.reload(routes_chat)
            assert routes_chat.CHAT_WS_REVALIDATE_SECONDS == 30
    finally:
        importlib.reload(routes_chat)


# =====================================================================
# CodeRabbit re-review fixes: report normalization, cleanup masking,
# in-flight upload reservation.
# =====================================================================


def test_distinct_reporter_count_excludes_missing_and_none_users():
    from app.social import moderation

    reports = [
        {"post": 5, "user": 1},
        {"post": 5, "user": None},   # None reporter must not count
        {"post": 5},                 # missing reporter must not count
        {"post": 5, "user": 1},      # duplicate of a valid reporter
        {"post": 9, "user": 2},      # different post
    ]
    assert moderation._distinct_reporter_count(reports, 5) == 1


def test_report_duplicate_normalizes_inflated_legacy_queue(tmp_path):
    from app.social import moderation

    store = tmp_path / "moderation_state.json"
    with (
        patch.object(moderation, "MODERATION_STORE_PATH", store),
        patch.object(moderation, "REPORT_THRESHOLD_AUTO_HIDE", 4),
        patch.object(moderation, "increment_reports", lambda: None),
    ):
        # Seed legacy state: one user's four duplicate rows inflated the queue
        # to reports=4/auto_hidden=True.
        def _seed(state):
            state["reports"] = [
                {"post": 555, "user": 101, "reason": "spam"} for _ in range(4)
            ]
            state["review_queue"] = [
                {"post_id": 555, "reports": 4, "auto_hidden": True}
            ]

        moderation._mutate_state(_seed)

        # A repeated report by the same user is idempotent but normalizes the
        # queue from DISTINCT reporters, correcting the inflated auto_hidden.
        moderation.report(user_id=101, post_id=555, reason="spam", target_user_id=999)

        queue = {item["post_id"]: item for item in moderation.get_review_queue()}
        assert queue[555]["reports"] == 1
        assert queue[555]["auto_hidden"] is False
        assert moderation.is_post_hidden(555) is False


def test_media_upload_cleanup_failure_does_not_mask_original(tmp_path):
    import pytest

    from app.api import routes_media
    from app.services import media_service

    db = _open_test_db_session()
    root = tmp_path / "media"
    user = SimpleNamespace(id=1)

    with (
        patch.object(media_service, "MEDIA_ROOT", root),
        patch.object(media_service, "MEDIA_MAX_MB", 5),
        patch.object(media_service, "increment_uploads", lambda: None),
        patch.object(media_service, "media_user_quota_bytes", return_value=10 ** 9),
        patch.object(media_service, "media_user_max_objects", return_value=1000),
        patch.object(routes_media, "create_media_asset", side_effect=RuntimeError("db down")),
        patch.object(routes_media, "remove_media_file", side_effect=OSError("cleanup boom")),
    ):
        # The original RuntimeError is observed, not the cleanup OSError.
        with pytest.raises(RuntimeError):
            asyncio.run(
                routes_media.media_upload(file=_FakeUpload(b"a" * 100), current_user=user, db=db)
            )


def test_media_inflight_reservation_bounds_concurrent_uploads_per_owner(tmp_path):
    import pytest
    from fastapi import HTTPException

    from app.services import media_service

    db = _open_test_db_session()
    root = tmp_path / "media"

    with (
        patch.object(media_service, "MEDIA_ROOT", root),
        patch.object(media_service, "MEDIA_MAX_MB", 5),
        patch.object(media_service, "media_inflight_max_per_owner", return_value=2),
        patch.object(media_service, "media_inflight_max_global", return_value=100),
    ):
        r1 = media_service.reserve_inflight_upload(db, owner_user_id=1)
        media_service.reserve_inflight_upload(db, owner_user_id=1)
        # A third concurrent in-flight upload for the same owner is rejected.
        with pytest.raises(HTTPException) as exc:
            media_service.reserve_inflight_upload(db, owner_user_id=1)
        assert exc.value.status_code == 429

        # Releasing one frees a slot; a different owner is unaffected.
        media_service.release_inflight_upload(db, r1)
        assert media_service.reserve_inflight_upload(db, owner_user_id=1) is not None
        assert media_service.reserve_inflight_upload(db, owner_user_id=2) is not None


def test_media_inflight_release_idempotent_and_ttl_reconciles(tmp_path):
    from datetime import datetime, timedelta

    from app.models import MediaUploadReservation
    from app.services import media_service

    db = _open_test_db_session()
    root = tmp_path / "media"

    with (
        patch.object(media_service, "MEDIA_ROOT", root),
        patch.object(media_service, "MEDIA_MAX_MB", 5),
        patch.object(media_service, "media_inflight_max_per_owner", return_value=1),
        patch.object(media_service, "media_inflight_max_global", return_value=100),
    ):
        r1 = media_service.reserve_inflight_upload(db, owner_user_id=1)
        # Double release and None are idempotent no-ops (never raise).
        media_service.release_inflight_upload(db, r1)
        media_service.release_inflight_upload(db, r1)
        media_service.release_inflight_upload(db, None)

        # A crash-abandoned (expired) reservation is reconciled on the next
        # acquire, freeing the owner's single slot.
        stale = MediaUploadReservation(
            owner_user_id=5,
            reserved_bytes=1,
            state="reserved",
            expires_at=datetime.utcnow() - timedelta(seconds=10),
        )
        db.add(stale)
        db.commit()
        assert media_service.reserve_inflight_upload(db, owner_user_id=5) is not None


def test_media_inflight_production_rejects_invalid_config():
    import os

    import pytest

    from app.services import media_service

    with (
        patch.dict(os.environ, {"MEDIA_INFLIGHT_MAX_PER_OWNER": "0"}),
        patch.object(media_service, "_current_env_normalized", return_value="production"),
    ):
        with pytest.raises(RuntimeError):
            media_service.media_inflight_max_per_owner()


def test_media_upload_route_reserves_before_streaming(tmp_path):
    import pytest
    from fastapi import HTTPException

    from app.api import routes_media
    from app.services import media_service

    db = _open_test_db_session()
    root = tmp_path / "media"
    user = SimpleNamespace(id=1)

    with (
        patch.object(media_service, "MEDIA_ROOT", root),
        patch.object(media_service, "increment_uploads", lambda: None),
        patch.object(
            routes_media,
            "reserve_inflight_upload",
            side_effect=HTTPException(status_code=429, detail="media_inflight_limit_owner"),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                routes_media.media_upload(file=_FakeUpload(b"a" * 100), current_user=user, db=db)
            )
        assert exc.value.status_code == 429
        # Rejection happens BEFORE streaming: no file was written.
        posts = root / "posts"
        assert not posts.exists() or list(posts.glob("*")) == []


def test_media_upload_fails_closed_in_production_before_any_write(tmp_path):
    import pytest
    from fastapi import HTTPException

    from app.api import routes_media
    from app.models import MediaAsset, MediaUploadReservation
    from app.services import media_service

    db = _open_test_db_session()
    root = tmp_path / "media"
    user = SimpleNamespace(id=1)

    with (
        patch.object(media_service, "MEDIA_ROOT", root),
        patch.object(media_service, "_current_env_normalized", return_value="production"),
        patch.object(routes_media, "reserve_inflight_upload") as reserve_mock,
        patch.object(routes_media, "save_upload") as save_mock,
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                routes_media.media_upload(file=_FakeUpload(b"a" * 100), current_user=user, db=db)
            )

    # Fail closed with a generic 503 — no reservation, no streaming, no bytes.
    assert exc.value.status_code == 503
    assert exc.value.detail == "media_upload_coordination_unavailable"
    reserve_mock.assert_not_called()
    save_mock.assert_not_called()
    assert not (root / "posts").exists() or list((root / "posts").glob("*")) == []
    assert db.query(MediaAsset).count() == 0
    assert db.query(MediaUploadReservation).count() == 0
    # The error leaks no dialect/path/internal detail.
    assert "sqlite" not in exc.value.detail.lower()
    assert "/" not in exc.value.detail


def test_media_upload_coordination_detection_exception_fails_closed():
    import pytest
    from fastapi import HTTPException

    from app.services import media_service

    with (
        patch.object(media_service, "_current_env_normalized", return_value="production"),
        patch.object(
            media_service, "media_upload_coordination_supported", side_effect=RuntimeError("boom")
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            media_service.ensure_media_upload_coordination_supported()
    assert exc.value.status_code == 503


def test_media_upload_coordination_gate_env_matrix():
    from app.services import media_service

    # Current build has no cross-replica coordinator -> production fails closed.
    with patch.object(media_service, "_current_env_normalized", return_value="production"):
        import pytest
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            media_service.ensure_media_upload_coordination_supported()
        assert exc.value.status_code == 503

    # If a shared coordinator were proven available, production would proceed.
    with (
        patch.object(media_service, "_current_env_normalized", return_value="production"),
        patch.object(media_service, "media_upload_coordination_supported", return_value=True),
    ):
        media_service.ensure_media_upload_coordination_supported()  # no raise

    # Dev/test always proceed with the host-local reservation.
    with patch.object(media_service, "_current_env_normalized", return_value="development"):
        media_service.ensure_media_upload_coordination_supported()  # no raise


def test_media_config_non_numeric_fails_closed_in_prod_else_default():
    import os

    import pytest

    from app.services import media_service

    config_fns = (
        ("MEDIA_USER_QUOTA_MB", media_service.media_user_quota_bytes),
        ("MEDIA_USER_MAX_OBJECTS", media_service.media_user_max_objects),
        ("MEDIA_INFLIGHT_MAX_PER_OWNER", media_service.media_inflight_max_per_owner),
    )
    for env_name, fn in config_fns:
        # Non-numeric value in production fails closed (RuntimeError), never an
        # escaping ValueError.
        with (
            patch.dict(os.environ, {env_name: "abc"}),
            patch.object(media_service, "_current_env_normalized", return_value="production"),
        ):
            with pytest.raises(RuntimeError):
                fn()
        # Non-numeric value in dev/test uses the established positive default.
        with (
            patch.dict(os.environ, {env_name: "abc"}),
            patch.object(media_service, "_current_env_normalized", return_value="development"),
        ):
            assert fn() > 0
