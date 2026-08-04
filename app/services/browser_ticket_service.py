import secrets
import threading
import time


TICKET_TTL_SECONDS = 30
_lock = threading.Lock()
# ponytail: process-local store; move to shared atomic cache before non-sticky multi-worker deployment.
_tickets: dict[str, dict] = {}


def issue_browser_ticket(*, user_id: int, display_name: str, scope: str, target: str) -> str:
    ticket = secrets.token_urlsafe(24)
    with _lock:
        now = time.time()
        expired = [key for key, value in _tickets.items() if value["expires_at"] <= now]
        for key in expired:
            _tickets.pop(key, None)
        _tickets[ticket] = {
            "user_id": user_id,
            "display_name": display_name,
            "scope": scope,
            "target": target,
            "expires_at": now + TICKET_TTL_SECONDS,
        }
    return ticket


def consume_browser_ticket(ticket: str, *, scope: str, target: str) -> dict | None:
    with _lock:
        key = str(ticket or "")
        payload = _tickets.get(key)
        if not payload:
            return None
        if payload["expires_at"] <= time.time():
            _tickets.pop(key, None)
            return None
        if payload["scope"] != scope or payload["target"] != target:
            return None
        return _tickets.pop(key)
