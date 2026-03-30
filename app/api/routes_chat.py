from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status

from app.database import SessionLocal
from app.dependencies import require_active_plan
from app.models import User
from app.security import resolve_token_user
from app.services.access_service import has_channel_access, refresh_user_access
from app.services.ticker_room_service import append_room_message, list_room_messages
from app.social.moderation import can_publish
from app.system.room_websocket_manager import room_ws_manager


class ChatMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=600)
    image_url: str | None = Field(default=None, max_length=2048)


router = APIRouter(tags=["Ticker Rooms"])


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
    symbol = symbol.upper()
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
    symbol = symbol.upper()
    allowed, reason = can_publish(current_user.id, payload.text)

    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    item = append_room_message(
        symbol=symbol,
        user_id=current_user.id,
        user_name=current_user.display_name or current_user.email,
        text=payload.text,
        image_url=payload.image_url,
    )

    if item is None:
        raise HTTPException(status_code=400, detail="chat_message_failed")

    await room_ws_manager.broadcast(
        symbol,
        {
            "type": "message",
            "item": item,
        },
    )
    return item


@router.websocket("/ws/chat/{symbol}")
async def websocket_chat(websocket: WebSocket, symbol: str):
    symbol = symbol.upper()
    token = websocket.query_params.get("token")
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
            payload = await websocket.receive_json()
            message_type = str(payload.get("type") or "message").lower()

            if message_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            text = str(payload.get("text") or "").strip()
            image_url = payload.get("image_url")
            allowed, reason = can_publish(user["id"], text)

            if not allowed:
                await websocket.send_json({"type": "error", "detail": reason})
                continue

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
