import logging

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.atomic_io import interprocess_file_lock
from app.dependencies import require_active_plan
from app.database import get_db
from app.models import User
from app.services.media_service import (
    enforce_media_quota,
    ensure_media_upload_coordination_supported,
    get_media_status,
    get_signed_upload,
    media_quota_lock_path,
    release_inflight_upload,
    remove_media_file,
    reserve_inflight_upload,
    save_upload,
)
from app.services.media_asset_service import create_media_asset, get_media_asset, serialize_media_asset

logger = logging.getLogger("stocknewsbr.media")


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
    # Fail closed FIRST, before any reservation, streaming, temp file or byte:
    # in production the in-flight reservation is only host-local, so uploads are
    # refused (503) until a shared cross-replica coordinator exists. Dev/test
    # proceed with the host-local reservation below.
    ensure_media_upload_coordination_supported()

    # In-flight admission control: reserve a persistent per-owner upload slot
    # BEFORE any bytes are streamed, so a burst of simultaneous uploads cannot
    # fill temporary storage before the persistent quota check runs. Slots are
    # coordinated per owner across workers via an interprocess lock and
    # persisted rows; crash-abandoned reservations are reconciled by TTL on
    # acquire. The reservation is always released on every exit path.
    reservation_id = reserve_inflight_upload(db, owner_user_id=current_user.id)

    try:
        payload = await save_upload(file, folder="posts")
        storage_key = f"{payload['folder']}/{payload['filename']}"

        # Persistent aggregate quota: the check and the asset insert run under a
        # per-owner interprocess lock so concurrent uploads (even across workers)
        # cannot both slip past the limit (no TOCTOU). Any failure before the
        # asset row is confirmed persisted (quota rejection, lock error, DB
        # error, unexpected error) removes the already-streamed file so it
        # consumes no disk or quota; a successfully created asset is never
        # deleted. The original exception (including HTTPException) is re-raised
        # untouched, and a cleanup failure never masks it.
        asset_created = False
        try:
            with interprocess_file_lock(media_quota_lock_path(current_user.id)):
                enforce_media_quota(db, owner_user_id=current_user.id, new_bytes=payload["size_bytes"])
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
                asset_created = True
        except Exception:
            if not asset_created:
                try:
                    remove_media_file(payload["folder"], payload["filename"])
                except Exception:
                    logger.warning("media upload cleanup failed after error")
            raise

        return {
            **payload,
            "asset": serialize_media_asset(asset),
        }
    finally:
        # Releasing the reservation must never mask the primary flow's
        # exception; the TTL sweep reclaims the slot as a safety net.
        try:
            release_inflight_upload(db, reservation_id)
        except Exception:
            logger.warning("failed to release in-flight upload reservation")


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
