import json
import os
import threading
import time
from pathlib import Path

from app.services.symbol_registry import canonical_symbol
from app.social.moderation import can_publish, record_content_approved, validate_attachment_url
from app.system.system_metrics import increment_chat_messages


ROOM_STORE_PATH = Path(os.getenv("ROOM_STORE_PATH", "data/ticker_rooms.json"))
_lock = threading.RLock()
MAX_ROOM_MESSAGES = 500


def _load_store():
    with _lock:
        if not ROOM_STORE_PATH.exists():
            return {}

        try:
            return json.loads(ROOM_STORE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}


def _save_store(store):
    with _lock:
        ROOM_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        ROOM_STORE_PATH.write_text(
            json.dumps(store, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )


def list_room_messages(symbol: str, limit: int = 100):
    symbol = canonical_symbol(symbol)
    store = _load_store()
    items = store.get(symbol, [])
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

    store = _load_store()
    items = list(store.get(symbol, []))

    message = {
        "id": f"{symbol}-{int(time.time() * 1000)}-{user_id}",
        "symbol": symbol,
        "user_id": user_id,
        "user_name": user_name or f"user_{user_id}",
        "text": text[:600],
        "image_url": image_url,
        "created_at": int(time.time()),
    }

    items.append(message)
    store[symbol] = items[-MAX_ROOM_MESSAGES:]
    _save_store(store)
    increment_chat_messages()
    record_content_approved(
        int(user_id),
        content_type="chat",
        content_id=message["id"],
        post_id=message["id"],
        ticker=symbol,
    )
    return message
