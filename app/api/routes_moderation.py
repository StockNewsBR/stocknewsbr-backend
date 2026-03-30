from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import require_any_channel_access
from app.models import User
from app.social.moderation import block, mute, report


class ModerationRequest(BaseModel):
    target: int | None = None
    post_id: int | None = None
    reason: str | None = None
    note: str | None = None


router = APIRouter(tags=["Moderation"])


@router.post("/mute")
def mute_user(
    payload: ModerationRequest,
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    if payload.target is None:
        raise HTTPException(status_code=400, detail="target_required")

    mute(current_user.id, payload.target)
    return {"status": "muted"}


@router.post("/block")
def block_user(
    payload: ModerationRequest,
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    if payload.target is None:
        raise HTTPException(status_code=400, detail="target_required")

    block(current_user.id, payload.target)
    return {"status": "blocked"}


@router.post("/report")
def report_post(
    payload: ModerationRequest,
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    if payload.post_id is None:
        raise HTTPException(status_code=400, detail="post_id_required")

    report(
        current_user.id,
        payload.post_id,
        reason=payload.reason,
        reporter_note=payload.note,
    )
    return {"status": "reported"}
