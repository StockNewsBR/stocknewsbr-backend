import os
import threading
import time
from pathlib import Path
from uuid import uuid4

from app.core.atomic_io import interprocess_file_lock, read_json_file, write_json_file_atomic
from app.services.symbol_registry import canonical_symbol
from app.social.moderation import can_publish, record_content_approved, validate_attachment_url
from app.system.system_metrics import increment_chat_messages


ROOM_STORE_PATH = Path(os.getenv("ROOM_STORE_PATH", "data/ticker_rooms.json"))
_lock = threading.RLock()
MAX_ROOM_MESSAGES = 500


def _load_store():
    with _lock:
        payload = read_json_file(ROOM_STORE_PATH, lambda: {})
        return payload if isinstance(payload, dict) else {}


def _save_store(store):
    with _lock:
        write_json_file_atomic(ROOM_STORE_PATH, store, ensure_ascii=True)


def list_room_messages(symbol: str, limit: int = 100):
    symbol = canonical_symbol(symbol)
    store = _load_store()
    items = [
        item
        for item in store.get(symbol, [])
        if item.get("status", "published") == "published"
    ]
    return items[-max(1, min(limit, MAX_ROOM_MESSAGES)) :]


def append_room_message(
    symbol: str,
    user_id: int,
    user_name: str,
    text: str,
    image_url: str | None = None,
):
    symbol = canonical_symbol(symbol)
    text = str(text or "").strip()

    if not symbol or not user_id or not text:
        return None

    allowed, reason = can_publish(int(user_id), text)
    if not allowed:
        return {"error": "chat_message_blocked", "reason": reason}

    attachment_allowed, attachment_reason = validate_attachment_url(int(user_id), image_url)
    if not attachment_allowed:
        return {"error": "chat_message_blocked", "reason": attachment_reason}

    lock_path = ROOM_STORE_PATH.with_suffix(".json.lock")

    message = {
        "id": f"{symbol}-{uuid4().hex}",
        "symbol": symbol,
        "user_id": user_id,
        "user_name": user_name or f"user_{user_id}",
        "text": text[:600],
        "image_url": image_url,
        "created_at": int(time.time()),
        "status": "pending_audit",
    }

    with _lock:
        with interprocess_file_lock(lock_path):
            store = _load_store()
            items = list(store.get(symbol, []))
            items.append(message)
            store[symbol] = items[-MAX_ROOM_MESSAGES:]
            _save_store(store)

    try:
        audit_record = record_content_approved(
            int(user_id),
            content_type="chat",
            content_id=message["id"],
            post_id=message["id"],
            ticker=symbol,
        )
        if audit_record is None:
            raise RuntimeError("ticker_room_audit_failed")
    except Exception:
        with _lock:
            with interprocess_file_lock(lock_path):
                store = _load_store()
                items = [
                    item
                    for item in list(store.get(symbol, []))
                    if item.get("id") != message["id"]
                ]
                store[symbol] = items[-MAX_ROOM_MESSAGES:]
                _save_store(store)
        return {"error": "chat_message_audit_failed", "reason": "ticker_room_audit_failed"}

    with _lock:
        with interprocess_file_lock(lock_path):
            store = _load_store()
            items = list(store.get(symbol, []))
            for item in items:
                if item.get("id") == message["id"]:
                    item["status"] = "published"
                    break
            store[symbol] = items[-MAX_ROOM_MESSAGES:]
            _save_store(store)

    message["status"] = "published"
    increment_chat_messages()
    return message
