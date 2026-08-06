from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.dependencies import require_active_plan
from app.database import apply_rls_context, get_db
from app.models import User
from app.services.media_service import get_media_status, get_signed_upload, save_upload
from app.services.media_asset_service import create_media_asset, get_media_asset, serialize_media_asset
from app.services.gif_service import search_tenor_gifs


class SignedUploadRequest(BaseModel):
    content_type: str = Field(..., min_length=3, max_length=64)
    folder: str = Field(default="posts", min_length=1, max_length=64)


router = APIRouter(prefix="/api/media", tags=["Media"])


def _apply_media_rls_context(db: Session, current_user: User) -> None:
    # Mission 36: bind the transaction-local RLS context to the authenticated
    # user before any media_assets access. Source of identity is ONLY the
    # authenticated user (never the request body/query/path). The auth/plan
    # dependency already ran a query on this same Session, so a transaction is
    # active; apply_rls_context is a no-op on SQLite and fail-closed on
    # PostgreSQL without an active transaction. Failure propagates (no
    # fallback without RLS).
    apply_rls_context(
        db,
        current_user_id=int(current_user.id),
        current_actor_id=int(current_user.id),
        current_role="user",
        request_id=None,
    )


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
    await run_in_threadpool(_apply_media_rls_context, db, current_user)
    payload = await save_upload(file, folder="posts")
    storage_key = f"{payload['folder']}/{payload['filename']}"
    asset = await run_in_threadpool(
        create_media_asset,
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
    _apply_media_rls_context(db, current_user)
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


@router.get("/gifs/search")
def media_gif_search(
    q: str,
    locale: str = "pt-BR",
    limit: int = 12,
    current_user: User = Depends(require_active_plan),
):
    del current_user
    return search_tenor_gifs(q, locale=locale, limit=limit)


@router.get("/{asset_id}")
def media_asset_detail(
    asset_id: int,
    current_user: User = Depends(require_active_plan),
    db: Session = Depends(get_db),
):
    _apply_media_rls_context(db, current_user)
    asset = get_media_asset(db, asset_id)

    if not asset or asset.owner_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="media_not_found")

    return serialize_media_asset(asset)
