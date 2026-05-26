from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import require_channel_access
from app.models import User
from app.services.help_center_service import get_help_center_blueprint, get_help_guide
from app.services.video_library_service import get_help_video_library
from app.services.workspace_service import get_workspace_data
from app.services.workspace_layout_service import (
    get_user_workspace_layout,
    save_user_workspace_layout,
)


class WorkspaceLayoutPayload(BaseModel):
    tabs: list[str] = Field(default_factory=list)
    pinned_ticker: str = Field(default="PETR4", max_length=16)
    opened_popouts: list[str] = Field(default_factory=list)
    chart_settings: dict = Field(default_factory=dict)


router = APIRouter(prefix="/web", tags=["web"])


@router.get("/workspace/data")
def workspace_data(current_user: User = Depends(require_channel_access("web"))):
    return get_workspace_data(user_id=current_user.id, channel="web")


@router.get("/workspace/layout")
def workspace_layout(current_user: User = Depends(require_channel_access("web"))):
    return get_user_workspace_layout(current_user.id)


@router.put("/workspace/layout")
def update_workspace_layout(
    payload: WorkspaceLayoutPayload,
    current_user: User = Depends(require_channel_access("web")),
):
    return save_user_workspace_layout(current_user.id, payload.model_dump())


@router.get("/help-center")
def workspace_help_center(current_user: User = Depends(require_channel_access("web"))):
    del current_user
    return get_help_center_blueprint()


@router.get("/help-center/{slug}")
def workspace_help_guide(
    slug: str,
    current_user: User = Depends(require_channel_access("web")),
):
    del current_user
    guide = get_help_guide(slug)

    if not guide:
        raise HTTPException(status_code=404, detail="guide_not_found")

    return guide


@router.get("/help-center/demo/{slug}")
def workspace_help_demo(
    slug: str,
    current_user: User = Depends(require_channel_access("web")),
):
    del current_user
    guide = get_help_guide(slug)

    if not guide:
        raise HTTPException(status_code=404, detail="guide_not_found")

    return {
        "slug": guide["slug"],
        "title": guide["title"],
        "mode": guide.get("demo_mode", "interactive_preview"),
        "video_ready": bool(guide.get("mp4_url")),
        "video_url": guide.get("mp4_url"),
        "next_step": (
            "Video MP4 disponivel."
            if guide.get("mp4_url")
            else "Gerar gravacao real ou video institucional quando o frontend final estiver fechado."
        ),
        "script": {
            "opening": guide.get("tagline"),
            "steps": guide.get("how_to_use", []),
            "example": guide.get("example"),
        },
    }


@router.get("/help-center/videos")
def workspace_help_videos(current_user: User = Depends(require_channel_access("web"))):
    del current_user
    return get_help_video_library()
