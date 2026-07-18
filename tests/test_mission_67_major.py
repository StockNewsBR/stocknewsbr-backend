import asyncio
import json
import tempfile
import threading
import time

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from app.core import telegram_timeout
from app.telegram import telegram_alert_engine
from app.engine.core import signal_fusion_v2
from app.data import warm_data_pool
from app.services import browser_ticket_service, media_service
from app.social import store as social_store


def _upload(payload: bytes) -> UploadFile:
    file = tempfile.SpooledTemporaryFile(max_size=len(payload) + 1)
    file.write(payload)
    file.seek(0)
    return UploadFile(
        file,
        filename="image.png",
        headers=Headers({"content-type": "image/png"}),
    )


def test_browser_ticket_is_scoped_expiring_and_single_use(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(browser_ticket_service.time, "time", lambda: now[0])
    ticket = browser_ticket_service.issue_browser_ticket(
        user_id=7, display_name="Trader", scope="chat", target="PETR4"
    )

    assert browser_ticket_service.consume_browser_ticket(ticket, scope="chat", target="VALE3") is None
    assert browser_ticket_service.consume_browser_ticket(ticket, scope="popout", target="PETR4") is None
    assert browser_ticket_service.consume_browser_ticket(ticket, scope="chat", target="PETR4")["user_id"] == 7
    assert browser_ticket_service.consume_browser_ticket(ticket, scope="chat", target="PETR4") is None

    expired = browser_ticket_service.issue_browser_ticket(
        user_id=7, display_name="Trader", scope="popout", target="grafico"
    )
    now[0] += browser_ticket_service.TICKET_TTL_SECONDS + 1
    assert browser_ticket_service.consume_browser_ticket(expired, scope="popout", target="grafico") is None
    assert expired not in browser_ticket_service._tickets


def test_warm_pool_checks_freshness_before_empty_universe(monkeypatch):
    now = time.time()
    monkeypatch.setattr(warm_data_pool, "_pool", {"PETR4": "cached"})
    monkeypatch.setattr(warm_data_pool, "_last_update", now)
    monkeypatch.setattr(warm_data_pool, "get_all_tickers", lambda: [])
    monkeypatch.setattr(warm_data_pool.time, "time", lambda: now)

    assert warm_data_pool.update_pool() == {"PETR4": "cached"}

    monkeypatch.setattr(warm_data_pool, "_last_update", now - warm_data_pool.WARM_POOL_TTL - 1)
    assert warm_data_pool.update_pool() == {}
    assert warm_data_pool.update_pool(force_refresh=True) == {}


def test_warm_pool_refresh_lock_avoids_duplicate_fetch(monkeypatch):
    calls = []
    frame = type("Frame", (), {"columns": ["Close"], "__len__": lambda self: 50, "dropna": lambda self, **kwargs: self})()
    monkeypatch.setattr(warm_data_pool, "_pool", {})
    monkeypatch.setattr(warm_data_pool, "_last_update", 0.0)
    monkeypatch.setattr(warm_data_pool, "get_all_tickers", lambda: ["PETR4"])
    monkeypatch.setattr(warm_data_pool.market_store, "update", lambda pool: None)

    def fetch(_tickers):
        calls.append(1)
        time.sleep(0.02)
        return frame

    monkeypatch.setattr(warm_data_pool, "get_market_data", fetch)
    results = []
    threads = [threading.Thread(target=lambda: results.append(warm_data_pool.update_pool())) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls == [1]
    assert results == [{"PETR4": frame}, {"PETR4": frame}]


def test_warm_pool_store_reader_waits_for_refresh_and_returns_copies(monkeypatch):
    fetch_started = threading.Event()
    release_fetch = threading.Event()
    store_reads = []
    frame = type(
        "Frame",
        (),
        {"columns": ["Close"], "__len__": lambda self: 50, "dropna": lambda self, **kwargs: self},
    )()
    monkeypatch.setattr(warm_data_pool, "_pool", {})
    monkeypatch.setattr(warm_data_pool, "_last_update", 0.0)
    monkeypatch.setattr(warm_data_pool, "get_all_tickers", lambda: ["PETR4"])
    monkeypatch.setattr(warm_data_pool.market_store, "update", lambda pool: None)
    monkeypatch.setattr(
        warm_data_pool.market_store,
        "get",
        lambda: store_reads.append(1) or {"VALE3": "stale"},
    )

    def fetch(_tickers):
        fetch_started.set()
        assert release_fetch.wait(timeout=1)
        return frame

    monkeypatch.setattr(warm_data_pool, "get_market_data", fetch)
    refreshed = []
    readers = []
    refresh = threading.Thread(target=lambda: refreshed.append(warm_data_pool.update_pool(force_refresh=True)))
    refresh.start()
    assert fetch_started.wait(timeout=1)
    reader_threads = [
        threading.Thread(target=lambda: readers.append(warm_data_pool.get_market_pool()))
        for _ in range(2)
    ]
    for reader in reader_threads:
        reader.start()
    release_fetch.set()
    refresh.join(timeout=1)
    for reader in reader_threads:
        reader.join(timeout=1)

    assert not refresh.is_alive()
    assert all(not reader.is_alive() for reader in reader_threads)
    assert refreshed == [{"PETR4": frame}]
    assert readers == [{"PETR4": frame}, {"PETR4": frame}]
    assert store_reads == []
    readers[0]["LOCAL"] = True
    assert "LOCAL" not in readers[1]


def test_media_folder_rejects_traversal_for_local_and_signed_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(media_service, "MEDIA_ROOT", tmp_path)

    with pytest.raises(HTTPException, match="invalid_media_folder"):
        asyncio.run(media_service.save_upload(_upload(b"ok"), folder="../outside"))
    with pytest.raises(HTTPException, match="invalid_media_folder"):
        media_service.get_signed_upload("image/png", folder="/tmp/outside")


def test_media_upload_streams_enforces_limit_and_removes_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(media_service, "MEDIA_ROOT", tmp_path)
    monkeypatch.setattr(media_service, "MEDIA_MAX_MB", 1)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(media_service.save_upload(_upload(b"x" * (1024 * 1024 + 1))))

    assert exc.value.status_code == 413
    assert exc.value.detail == "media_too_large"
    assert not list(tmp_path.rglob("*.tmp"))
    assert not list(tmp_path.rglob("*.png"))


@pytest.mark.parametrize("payload,detail", [(b"", "empty_media_file"), (b"not-a-png", "invalid_media_content")])
def test_media_upload_rejects_empty_or_spoofed_images_without_partial(tmp_path, monkeypatch, payload, detail):
    monkeypatch.setattr(media_service, "MEDIA_ROOT", tmp_path)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(media_service.save_upload(_upload(payload)))

    assert exc.value.status_code == 400
    assert exc.value.detail == detail
    assert not list(tmp_path.rglob("*.tmp"))
    assert not list(tmp_path.rglob("*.png"))


def test_media_upload_persists_valid_png_with_public_path(tmp_path, monkeypatch):
    monkeypatch.setattr(media_service, "MEDIA_ROOT", tmp_path)
    png = b"\x89PNG\r\n\x1a\n" + b"valid-test-payload"

    payload = asyncio.run(media_service.save_upload(_upload(png)))

    assert payload["url"].startswith("/media/posts/")
    assert not payload["url"].startswith(("blob:", "file:"))
    assert (tmp_path / "posts" / payload["filename"]).read_bytes() == png


def test_social_store_does_not_replace_malformed_state(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(social_store, "SOCIAL_STORE_PATH", path)

    with pytest.raises(json.JSONDecodeError):
        social_store.mutate_social_state(lambda state: state["posts"].append({"id": 1}))

    assert path.read_text(encoding="utf-8") == "{broken"


def test_social_store_read_failure_propagates_without_writing(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text('{"posts": []}', encoding="utf-8")
    monkeypatch.setattr(social_store, "SOCIAL_STORE_PATH", path)
    monkeypatch.setattr(type(path), "read_text", lambda self, **kwargs: (_ for _ in ()).throw(OSError("busy")))
    writes = []
    monkeypatch.setattr(social_store, "_write_to_disk", lambda state: writes.append(state))

    with pytest.raises(OSError, match="busy"):
        social_store.mutate_social_state(lambda state: state["posts"].append({"id": 1}))

    assert writes == []


def test_social_store_missing_file_still_returns_default(tmp_path, monkeypatch):
    monkeypatch.setattr(social_store, "SOCIAL_STORE_PATH", tmp_path / "missing.json")

    state = social_store.read_social_state(lambda value: value)

    assert state == social_store._default_state()


def test_telegram_retry_policies_keep_post_scopes_separate():
    generic = telegram_timeout.retry_strategy
    send_message = telegram_alert_engine.retry

    assert "POST" not in generic.allowed_methods
    assert generic.allowed_methods == frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PUT"})
    assert telegram_timeout.session.get_adapter("https://").max_retries is generic
    assert "POST" in send_message.allowed_methods
    assert set(send_message.status_forcelist) == {429}


def test_signal_fusion_ranks_before_limit(monkeypatch):
    monkeypatch.setattr(signal_fusion_v2, "MAX_SIGNALS", 2)
    monkeypatch.setattr(signal_fusion_v2, "compute_score", lambda row: row["score"])

    result = signal_fusion_v2.run_signal_fusion([{"score": 1}, {"score": 2}, {"score": 100}])

    assert [row["fusion_score"] for row in result] == [100, 2]
