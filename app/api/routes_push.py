from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import require_active_plan, require_internal_token
from app.models import User
from app.services.push_service import (
    get_push_status,
    list_push_tokens,
    register_push_token,
    send_push_notification,
    unregister_push_token,
)


class PushRegisterRequest(BaseModel):
    token: str = Field(..., min_length=16, max_length=4096)
    platform: str = Field(default="android", min_length=3, max_length=16)
    app_version: str | None = Field(default=None, max_length=64)


class PushUnregisterRequest(BaseModel):
    token: str = Field(..., min_length=16, max_length=4096)


class PushSendRequest(BaseModel):
    user_id: int
    title: str = Field(..., min_length=1, max_length=120)
    body: str = Field(..., min_length=1, max_length=240)
    data: dict[str, str] = Field(default_factory=dict)


router = APIRouter(tags=["Push"])


@router.get("/push/status")
def push_status(current_user: User = Depends(require_active_plan)):
    del current_user
    return get_push_status()


@router.get("/push/tokens")
def push_tokens(current_user: User = Depends(require_active_plan)):
    return {"items": list_push_tokens(current_user.id)}


@router.post("/push/register")
def push_register(
    payload: PushRegisterRequest,
    current_user: User = Depends(require_active_plan),
):
    result = register_push_token(
        user_id=current_user.id,
        token=payload.token,
        platform=payload.platform,
        app_version=payload.app_version,
    )

    if result is None:
        raise HTTPException(status_code=400, detail="push_registration_failed")

    return result


@router.post("/push/unregister")
def push_unregister(
    payload: PushUnregisterRequest,
    current_user: User = Depends(require_active_plan),
):
    return unregister_push_token(current_user.id, payload.token)


@router.post("/push/test-send")
def push_test_send(
    payload: PushSendRequest,
    _internal=Depends(require_internal_token),
):
    del _internal
    return send_push_notification(
        user_id=payload.user_id,
        title=payload.title,
        body=payload.body,
        data=payload.data,
    )
