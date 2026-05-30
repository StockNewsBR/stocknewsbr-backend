import json
import os
import threading
import time
from pathlib import Path

from app.system.system_metrics import increment_push_sends


try:
    import firebase_admin
    from firebase_admin import credentials, messaging
except Exception:  # pragma: no cover - optional dependency
    firebase_admin = None
    credentials = None
    messaging = None


PUSH_STORE_PATH = Path("data/push_tokens.json")
_lock = threading.RLock()
_firebase_app = None


def _load_store():
    with _lock:
        if not PUSH_STORE_PATH.exists():
            return {}

        try:
            return json.loads(PUSH_STORE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}


def _save_store(store):
    with _lock:
        PUSH_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PUSH_STORE_PATH.write_text(
            json.dumps(store, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )


def _firebase_ready():
    return bool(
        firebase_admin
        and (
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            or os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        )
    )


def _get_firebase_app():
    global _firebase_app

    if not _firebase_ready():
        return None

    if _firebase_app is not None:
        return _firebase_app

    try:
        service_account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()

        if service_account_json:
            cred = credentials.Certificate(json.loads(service_account_json))
        elif service_account_path:
            cred = credentials.Certificate(service_account_path)
        else:
            return None

        _firebase_app = firebase_admin.initialize_app(cred)
        return _firebase_app
    except Exception:
        return None


def register_push_token(user_id: int, token: str, platform: str, app_version: str | None = None):
    if not user_id or not token:
        return None

    store = _load_store()
    items = list(store.get(str(user_id), []))
    token = token.strip()
    platform = (platform or "android").strip().lower()
    items = [item for item in items if item.get("token") != token]
    items.append(
        {
            "token": token,
            "platform": platform,
            "app_version": app_version,
            "registered_at": int(time.time()),
        }
    )
    store[str(user_id)] = items[-10:]
    _save_store(store)
    return {"user_id": user_id, "tokens": store[str(user_id)]}


def unregister_push_token(user_id: int, token: str):
    store = _load_store()
    items = [item for item in store.get(str(user_id), []) if item.get("token") != token]
    store[str(user_id)] = items
    _save_store(store)
    return {"user_id": user_id, "tokens": items}


def list_push_tokens(user_id: int):
    return list(_load_store().get(str(user_id), []))


def get_push_token_store():
    return _load_store()


def send_push_notification(
    user_id: int,
    title: str,
    body: str,
    data: dict | None = None,
    tokens: list[dict] | None = None,
):
    resolved_tokens = list(tokens) if tokens is not None else list_push_tokens(user_id)

    if not resolved_tokens:
        return {"sent": 0, "reason": "no_registered_tokens"}

    app = _get_firebase_app()

    if app is None or messaging is None:
        return {
            "sent": 0,
            "reason": "firebase_not_configured",
            "tokens": len(resolved_tokens),
        }

    sent = 0

    for item in resolved_tokens:
        try:
            message = messaging.Message(
                token=item["token"],
                notification=messaging.Notification(title=title, body=body),
                data={str(key): str(value) for key, value in (data or {}).items()},
            )
            messaging.send(message, app=app)
            sent += 1
            increment_push_sends()
        except Exception:
            continue

    return {"sent": sent, "tokens": len(resolved_tokens)}


def get_push_status():
    android_ready = bool(
        os.getenv("FIREBASE_PROJECT_ID")
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        or os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    )
    apple_ready = all(
        [
            os.getenv("APNS_KEY_ID"),
            os.getenv("APNS_TEAM_ID"),
            os.getenv("APNS_BUNDLE_ID"),
        ]
    )

    missing_android = []
    missing_apple = []

    if not android_ready:
        missing_android = [
            "FIREBASE_PROJECT_ID",
            "GOOGLE_APPLICATION_CREDENTIALS ou FIREBASE_SERVICE_ACCOUNT_JSON",
        ]

    if not apple_ready:
        missing_apple = ["APNS_KEY_ID", "APNS_TEAM_ID", "APNS_BUNDLE_ID"]

    store = _load_store()
    total_tokens = sum(len(items) for items in store.values())

    return {
        "android_ready": android_ready,
        "apple_ready": apple_ready,
        "firebase_sdk_available": firebase_admin is not None,
        "registered_tokens": total_tokens,
        "providers": {
            "android": "firebase",
            "apple": "apns",
        },
        "missing_android": missing_android,
        "missing_apple": missing_apple,
        "next_step": (
            "Instalar/configurar Firebase Admin e credenciais para envio real."
            if not _firebase_ready()
            else "Push Android pronto para testes reais."
        ),
    }
