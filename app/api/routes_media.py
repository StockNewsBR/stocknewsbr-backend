from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.dependencies import require_active_plan
from app.database import get_db
from app.models import User
from app.services.media_service import get_media_status, get_signed_upload, save_upload
from app.services.media_asset_service import create_media_asset, get_media_asset, serialize_media_asset


class SignedUploadRequest(BaseModel):
    content_type: str = Field(..., min_length=3, max_length=64)
    folder: str = Field(default="posts", min_length=1, max_length=64)


router = APIRouter(prefix="/api/media", tags=["Media"])


@router.get("/status")
def media_status(current_user: User = Depends(require_active_plan)):
    del current_user
    return get_media_status()


@router.post("/upload")
async def media_upload(
    file: UploadFile = File(...),
    current_user: User = Depends(require_active_plan),
    db: Session = Depends(get_db),
):
    payload = await save_upload(file, folder="posts")
    storage_key = f"{payload['folder']}/{payload['filename']}"
    asset = create_media_asset(
        db,
        owner_user_id=current_user.id,
        provider=payload["provider"],
        folder=payload["folder"],
        filename=payload["filename"],
        storage_key=storage_key,
        content_type=payload["content_type"],
        size_bytes=payload["size_bytes"],
        public_url=payload["url"],
        status="uploaded",
    )
    return {
        **payload,
        "asset": serialize_media_asset(asset),
    }


@router.post("/presign")
def media_presign(
    payload: SignedUploadRequest,
    current_user: User = Depends(require_active_plan),
    db: Session = Depends(get_db),
):
    signed = get_signed_upload(
        content_type=payload.content_type,
        folder=payload.folder,
    )
    filename = str(signed.get("key") or "upload").split("/")[-1]
    asset = create_media_asset(
        db,
        owner_user_id=current_user.id,
        provider=str(signed.get("provider") or "local"),
        folder=payload.folder,
        filename=filename,
        storage_key=signed.get("key"),
        content_type=payload.content_type,
        public_url=signed.get("public_url"),
        status="pending_upload",
    )
    return {
        **signed,
        "asset": serialize_media_asset(asset),
    }


@router.get("/{asset_id}")
def media_asset_detail(
    asset_id: int,
    current_user: User = Depends(require_active_plan),
    db: Session = Depends(get_db),
):
    asset = get_media_asset(db, asset_id)

    if not asset or asset.owner_user_id != current_user.id:
        return {"detail": "media_not_found"}

    return serialize_media_asset(asset)
