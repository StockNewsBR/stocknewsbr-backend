import json
import os
import threading
import time
from pathlib import Path

from app.core.atomic_io import write_json_file_atomic
from app.system.kill_switches import alert_channel_block_reason
from app.system.system_metrics import increment_push_sends


# Mission 32: classificação de erro de envio para fake transports/testes.
class PushSendError(Exception):
    """Erro temporário de envio (elegível a retry pelo ciclo seguinte)."""


class PushTokenInvalidError(PushSendError):
    """Token permanentemente inválido: desativar, nunca re-tentar."""


# Nomes de exceção do Firebase Admin que indicam token inválido permanente.
_FIREBASE_INVALID_TOKEN_ERRORS = {
    "UnregisteredError",
    "SenderIdMismatchError",
    "InvalidArgumentError",
}


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
        # Mission 31F: escrita atômica; o write_text direto podia deixar JSON
        # parcial em disco se o processo caísse no meio da gravação.
        write_json_file_atomic(PUSH_STORE_PATH, store, ensure_ascii=True)


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


def mask_push_token(token) -> str:
    """Representação pública do token: nunca expor o valor bruto."""
    text = str(token or "")
    if len(text) < 12:
        return "***"
    return f"{text[:4]}...{text[-4:]}"


def _public_token_item(item: dict) -> dict:
    # Mission 32: respostas públicas usam token mascarado, nunca o bruto.
    safe = {key: value for key, value in dict(item or {}).items() if key != "token"}
    safe["token_masked"] = mask_push_token((item or {}).get("token"))
    return safe


def register_push_token(user_id: int, token: str, platform: str, app_version: str | None = None):
    if not user_id or not token:
        return None

    # Mission 31F: o ciclo load-modify-save precisa ser atômico; sem o lock
    # cobrindo a operação inteira, registros concorrentes se sobrescrevem.
    with _lock:
        store = _load_store()
        token = token.strip()
        if not token:
            return None
        platform = (platform or "android").strip().lower()

        # Mission 32: um device token pertence a um único usuário. Política
        # explícita: re-registro atualiza o vínculo (remove o token de
        # qualquer outro usuário antes de associá-lo ao usuário atual).
        for other_key in list(store.keys()):
            if other_key == str(user_id):
                continue
            remaining = [item for item in store.get(other_key, []) if item.get("token") != token]
            if len(remaining) != len(store.get(other_key, [])):
                store[other_key] = remaining

        items = list(store.get(str(user_id), []))
        items = [item for item in items if item.get("token") != token]
        items.append(
            {
                "token": token,
                "platform": platform,
                "app_version": app_version,
                "registered_at": int(time.time()),
                "active": True,
            }
        )
        store[str(user_id)] = items[-10:]
        _save_store(store)
        return {"user_id": user_id, "tokens": [_public_token_item(item) for item in store[str(user_id)]]}


def unregister_push_token(user_id: int, token: str):
    with _lock:
        store = _load_store()
        items = [item for item in store.get(str(user_id), []) if item.get("token") != token]
        store[str(user_id)] = items
        _save_store(store)
        return {"user_id": user_id, "tokens": [_public_token_item(item) for item in items]}


def deactivate_push_token(user_id: int, token: str, reason: str = "provider_invalid_token"):
    """Marca o token como inativo (erro permanente do provider).

    Não apaga a evidência: o registro permanece com motivo sanitizado e
    timestamp, e um novo registro do mesmo token reativa o vínculo.
    """
    with _lock:
        store = _load_store()
        changed = False
        for item in store.get(str(user_id), []):
            if item.get("token") == token and item.get("active", True):
                item["active"] = False
                item["deactivated_reason"] = str(reason or "provider_invalid_token")[:80]
                item["deactivated_at"] = int(time.time())
                changed = True
        if changed:
            _save_store(store)
        return changed


def list_push_tokens(user_id: int, include_inactive: bool = False):
    items = list(_load_store().get(str(user_id), []))
    if include_inactive:
        return items
    return [item for item in items if item.get("active", True)]


def list_push_tokens_public(user_id: int):
    """Versão pública (rotas): tokens sempre mascarados."""
    return [_public_token_item(item) for item in list_push_tokens(user_id, include_inactive=True)]


def get_push_token_store():
    return _load_store()


def _classify_send_error(exc: Exception) -> str:
    """Classifica o erro do provider: 'invalid_token' (permanente) ou
    'temporary'. Baseado na documentação do Firebase Admin (nomes de
    exceção); nunca inspeciona o token em si."""
    if isinstance(exc, PushTokenInvalidError):
        return "invalid_token"
    if isinstance(exc, PushSendError):
        return "temporary"
    if type(exc).__name__ in _FIREBASE_INVALID_TOKEN_ERRORS:
        return "invalid_token"
    return "temporary"


def send_push_notification(
    user_id: int,
    title: str,
    body: str,
    data: dict | None = None,
    tokens: list[dict] | None = None,
    sender=None,
):
    """Envia push para os tokens ativos do usuário.

    `sender(token, title, body, data)` permite fake transport em testes;
    quando ausente, usa o Firebase Admin. Erros permanentes de token
    desativam somente o token afetado (sem retry); erros temporários não
    desativam nada. Uma única tentativa por token por ciclo (o retry entre
    ciclos é responsabilidade do dispatcher/worker).
    """
    # Mission 32: kill switch fail-safe também na borda do provider.
    kill_reason = alert_channel_block_reason("push")
    if kill_reason:
        return {"sent": 0, "reason": kill_reason, "tokens": 0}

    resolved_tokens = list(tokens) if tokens is not None else list_push_tokens(user_id)
    resolved_tokens = [item for item in resolved_tokens if item.get("active", True)]

    if not resolved_tokens:
        return {"sent": 0, "reason": "no_registered_tokens", "tokens": 0}

    if sender is None:
        app = _get_firebase_app()

        if app is None or messaging is None:
            return {
                "sent": 0,
                "reason": "firebase_not_configured",
                "tokens": len(resolved_tokens),
            }

        def sender(token, sender_title, sender_body, sender_data):
            message = messaging.Message(
                token=token,
                notification=messaging.Notification(title=sender_title, body=sender_body),
                data={str(key): str(value) for key, value in (sender_data or {}).items()},
            )
            messaging.send(message, app=app)

    sent = 0
    failed = 0
    invalidated = 0

    for item in resolved_tokens:
        try:
            sender(item["token"], title, body, data or {})
            sent += 1
            increment_push_sends()
        except Exception as exc:
            if _classify_send_error(exc) == "invalid_token":
                deactivate_push_token(user_id, item.get("token"), reason=type(exc).__name__)
                invalidated += 1
            else:
                failed += 1
            continue

    return {
        "sent": sent,
        "failed": failed,
        "invalidated": invalidated,
        "tokens": len(resolved_tokens),
    }


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
    push_block_reason = alert_channel_block_reason("push")

    return {
        "android_ready": android_ready,
        "apple_ready": apple_ready,
        "push_alerts_disabled": push_block_reason is not None,
        "push_block_reason": push_block_reason,
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
