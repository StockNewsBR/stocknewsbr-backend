import asyncio
import os

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status

from app.core.csrf import allowed_web_origins, origin_from_header
from app.core.settings import session_cookie_name
from app.database import SessionLocal
from app.dependencies import require_active_plan
from app.models import User
from app.security import resolve_token_user
from app.services.access_service import has_channel_access, refresh_user_access
from app.services.symbol_registry import canonical_symbol
from app.services.ticker_room_service import append_room_message, list_room_messages
from app.system.room_websocket_manager import room_ws_manager


class ChatMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=600)
    image_url: str | None = Field(default=None, max_length=2048)


router = APIRouter(tags=["Ticker Rooms"])

# Chat WebSocket authorization is revalidated against the authoritative session
# store instead of being frozen at the handshake. The interval bounds how long a
# revoked/expired/logged-out session can linger on an otherwise idle socket; it
# is always >= 1s so production never gets a zero/negative (busy-loop) interval.
try:
    # Non-numeric/invalid config must never crash import; fall back to the safe
    # default. Valid values keep the >= 1s minimum (never zero/negative).
    CHAT_WS_REVALIDATE_SECONDS = max(1, int(os.getenv("CHAT_WS_REVALIDATE_SECONDS", "30")))
except (TypeError, ValueError):
    CHAT_WS_REVALIDATE_SECONDS = 30


def _resolve_user_from_token(token: str | None):
    if not token:
        return None

    db = SessionLocal()

    try:
        user = resolve_token_user(token, db)

        refresh_user_access(user)

        if not user.is_active or not has_channel_access(user):
            return None

        return {
            "id": user.id,
            "display_name": user.display_name or user.email,
        }
    except Exception:
        return None
    finally:
        db.close()


@router.get("/chat/{symbol}/history")
def chat_history(
    symbol: str,
    limit: int = 100,
    current_user: User = Depends(require_active_plan),
):
    del current_user
    symbol = canonical_symbol(symbol)
    return {
        "symbol": symbol,
        "items": list_room_messages(symbol, limit=limit),
    }


@router.post("/chat/{symbol}/message")
async def chat_message(
    symbol: str,
    payload: ChatMessageRequest,
    current_user: User = Depends(require_active_plan),
):
    symbol = canonical_symbol(symbol)
    item = append_room_message(
        symbol=symbol,
        user_id=current_user.id,
        user_name=current_user.display_name or current_user.email,
        text=payload.text,
        image_url=payload.image_url,
    )

    if item is None:
        raise HTTPException(status_code=400, detail="chat_message_failed")
    if isinstance(item, dict) and item.get("error"):
        raise HTTPException(status_code=429, detail=item.get("reason", "chat_message_blocked"))

    await room_ws_manager.broadcast(
        symbol,
        {
            "type": "message",
            "item": item,
        },
    )
    return item


def _cookie_websocket_origin_allowed(websocket: WebSocket) -> bool:
    """CSWSH guard: cookie-authenticated handshakes need an allowed Origin."""
    origin = origin_from_header(websocket.headers.get("origin"))
    return origin in set(allowed_web_origins())


def _authorization_websocket_bearer(websocket: WebSocket) -> str | None:
    authorization = str(websocket.headers.get("authorization") or "").strip()
    scheme, separator, token = authorization.partition(" ")

    if separator and scheme.lower() == "bearer" and token.strip():
        return token.strip()

    return None


@router.websocket("/ws/chat/{symbol}")
async def websocket_chat(websocket: WebSocket, symbol: str):
    symbol = canonical_symbol(symbol)
    cookie_token = websocket.cookies.get(session_cookie_name())

    if cookie_token and not _cookie_websocket_origin_allowed(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Browser clients use the httpOnly cookie. Non-browser clients may use an
    # Authorization header, but reusable bearer credentials are never accepted
    # from a query string.
    token = cookie_token or _authorization_websocket_bearer(websocket)

    user = _resolve_user_from_token(token)

    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await room_ws_manager.connect(symbol, websocket)
    await websocket.send_json(
        {
            "type": "history",
            "symbol": symbol,
            "items": list_room_messages(symbol, limit=60),
        }
    )

    try:
        while True:
            try:
                payload = await asyncio.wait_for(
                    websocket.receive_json(), timeout=CHAT_WS_REVALIDATE_SECONDS
                )
            except asyncio.TimeoutError:
                # Idle socket: revalidate so a revoked/expired session on a
                # silent connection is still torn down within the interval.
                if _resolve_user_from_token(token) is None:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                continue

            # Revalidate against the authoritative session store before ANY
            # action (including ping): logout, revocation, expiry or a
            # deactivated user must stop the socket, not stay frozen from the
            # handshake. Ping cannot bypass this.
            refreshed = _resolve_user_from_token(token)
            if refreshed is None:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            user = refreshed

            message_type = str(payload.get("type") or "message").lower()

            if message_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            text = str(payload.get("text") or "").strip()
            image_url = payload.get("image_url")

            item = append_room_message(
                symbol=symbol,
                user_id=user["id"],
                user_name=user["display_name"],
                text=text,
                image_url=image_url,
            )

            if item is None:
                await websocket.send_json({"type": "error", "detail": "chat_message_failed"})
                continue
            if isinstance(item, dict) and item.get("error"):
                await websocket.send_json({"type": "error", "detail": item.get("reason", "chat_message_blocked")})
                continue

            await room_ws_manager.broadcast(
                symbol,
                {
                    "type": "message",
                    "item": item,
                },
            )
    except WebSocketDisconnect:
        pass
    finally:
        room_ws_manager.disconnect(symbol, websocket)
