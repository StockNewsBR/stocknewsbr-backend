import asyncio
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.atomic_io import interprocess_file_lock
from app.core.settings import _current_env_normalized
from app.models import MediaAsset, MediaUploadReservation
from app.services.storage_service import (
    STORAGE_PROVIDER,
    build_public_url,
    build_storage_key,
    create_presigned_upload,
    get_storage_status,
)
from app.system.system_metrics import increment_uploads

# Assets in these states occupy the owner's persistent quota (bytes are read
# from the MediaAsset rows, so deleting a row frees quota with no double-count).
ACTIVE_MEDIA_STATUSES = ("uploaded", "pending_upload")

MEDIA_ROOT = Path(os.getenv("MEDIA_UPLOAD_DIR", "media")).resolve()
MEDIA_PUBLIC_PREFIX = os.getenv("MEDIA_PUBLIC_PREFIX", "/media").strip() or "/media"
MEDIA_PUBLIC_BASE_URL = os.getenv("MEDIA_PUBLIC_BASE_URL", "").strip()
MEDIA_MAX_MB = max(1, int(os.getenv("MEDIA_MAX_MB", "12")))
UPLOAD_CHUNK_SIZE = 64 * 1024

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def ensure_media_root():
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    return MEDIA_ROOT


def get_media_status():
    ensure_media_root()
    storage_status = get_storage_status()

    return {
        "provider": STORAGE_PROVIDER,
        "local_storage_ready": MEDIA_ROOT.exists(),
        "max_upload_mb": MEDIA_MAX_MB,
        "allowed_content_types": sorted(ALLOWED_CONTENT_TYPES),
        "public_prefix": MEDIA_PUBLIC_PREFIX,
        "cdn_ready": storage_status["signed_upload_supported"] or bool(MEDIA_PUBLIC_BASE_URL and STORAGE_PROVIDER != "local"),
        "public_base_url": MEDIA_PUBLIC_BASE_URL or None,
        "storage": storage_status,
        "next_step": (
            "Configurar MEDIA_PUBLIC_BASE_URL e um provider externo como R2/S3 para CDN real."
            if STORAGE_PROVIDER == "local"
            else "Validar bucket, CORS e dominio publico do provider configurado."
        ),
    }


async def save_upload(file: UploadFile, folder: str = "posts"):
    ensure_media_root()

    content_type = (file.content_type or "").lower().strip()

    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="unsupported_media_type")

    extension = ALLOWED_CONTENT_TYPES[content_type]
    directory = MEDIA_ROOT / folder
    directory.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid4().hex}{extension}"
    destination = directory / filename
    max_size_bytes = MEDIA_MAX_MB * 1024 * 1024

    # Stream the upload to a temporary file with a hard byte cap. The body is
    # never read in a single call, so an oversized upload cannot be fully
    # materialized in memory (peak memory is bounded to one chunk). The temp
    # file lives in the destination directory so it can be promoted with an
    # atomic rename; any partial artifact is removed on rejection or error.
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=".upload-", suffix=".part", dir=str(directory))
    total = 0

    try:
        with os.fdopen(tmp_fd, "wb") as tmp:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_size_bytes:
                    raise HTTPException(status_code=413, detail="media_too_large")
                # Offload blocking disk writes so a large upload never stalls
                # the async event loop.
                await asyncio.to_thread(tmp.write, chunk)
        await asyncio.to_thread(os.replace, tmp_name, destination)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    size_bytes = total
    increment_uploads()

    relative_url = f"{MEDIA_PUBLIC_PREFIX.rstrip('/')}/{folder}/{filename}"
    absolute_url = f"{MEDIA_PUBLIC_BASE_URL.rstrip('/')}/{folder}/{filename}" if MEDIA_PUBLIC_BASE_URL else relative_url

    return {
        "provider": STORAGE_PROVIDER,
        "folder": folder,
        "filename": filename,
        "content_type": content_type,
        "size_bytes": size_bytes,
        "url": absolute_url,
        "relative_url": relative_url,
    }


def get_signed_upload(content_type: str, folder: str = "posts"):
    content_type = (content_type or "").lower().strip()

    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="unsupported_media_type")

    extension = ALLOWED_CONTENT_TYPES[content_type]
    payload = create_presigned_upload(folder=folder, extension=extension, content_type=content_type)

    if payload is None:
        key = build_storage_key(folder, extension)
        return {
            "provider": STORAGE_PROVIDER,
            "fallback_local_upload": True,
            "key": key,
            "public_url": build_public_url(key),
        }

    return payload


def _int_env(name: str, default: str) -> int:
    # A non-numeric/invalid value is treated like other invalid input (0), so
    # production fails closed via the caller's RuntimeError and non-production
    # falls back to the established default — never an escaping ValueError.
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return 0


def media_user_quota_bytes() -> int:
    raw_mb = _int_env("MEDIA_USER_QUOTA_MB", "200")
    if raw_mb <= 0:
        if _current_env_normalized() == "production":
            raise RuntimeError("MEDIA_USER_QUOTA_MB_REQUIRED_IN_PRODUCTION")
        raw_mb = 200
    return raw_mb * 1024 * 1024


def media_user_max_objects() -> int:
    raw = _int_env("MEDIA_USER_MAX_OBJECTS", "500")
    if raw <= 0:
        if _current_env_normalized() == "production":
            raise RuntimeError("MEDIA_USER_MAX_OBJECTS_REQUIRED_IN_PRODUCTION")
        raw = 500
    return raw


def media_quota_lock_path(owner_user_id: int) -> Path:
    ensure_media_root()
    return MEDIA_ROOT / f".quota-{int(owner_user_id)}.lock"


def current_media_usage(db: Session, owner_user_id: int) -> tuple[int, int]:
    """Persistent per-owner usage read from the MediaAsset rows themselves."""
    used = (
        db.query(func.coalesce(func.sum(MediaAsset.size_bytes), 0))
        .filter(
            MediaAsset.owner_user_id == owner_user_id,
            MediaAsset.status.in_(ACTIVE_MEDIA_STATUSES),
        )
        .scalar()
        or 0
    )
    count = (
        db.query(func.count(MediaAsset.id))
        .filter(
            MediaAsset.owner_user_id == owner_user_id,
            MediaAsset.status.in_(ACTIVE_MEDIA_STATUSES),
        )
        .scalar()
        or 0
    )
    return int(used), int(count)


def enforce_media_quota(db: Session, *, owner_user_id: int, new_bytes: int) -> None:
    """Reject the upload if it would push the owner past the persistent quota.

    Usage is derived from committed MediaAsset rows, so a deleted asset frees
    quota automatically (no separate release, no double-free). Callers MUST run
    this together with the asset insert under ``media_quota_lock_path`` so the
    check-then-reserve is atomic across concurrent uploads/workers.
    """
    used, count = current_media_usage(db, owner_user_id)

    if used + int(new_bytes) > media_user_quota_bytes():
        raise HTTPException(status_code=413, detail="media_quota_exceeded")

    if count + 1 > media_user_max_objects():
        raise HTTPException(status_code=413, detail="media_object_limit_exceeded")


def remove_media_file(folder: str, filename: str) -> None:
    try:
        root = MEDIA_ROOT.resolve()
        candidate = (root / folder / filename).resolve()
        # Confine strictly inside MEDIA_ROOT before unlinking: reject `..`
        # traversal, absolute folder/filename components and symlinks that
        # resolve outside the root, and never delete the root itself. Internal
        # paths are never surfaced to callers.
        if candidate == root or not candidate.is_relative_to(root):
            return
        if candidate.exists():
            candidate.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# In-flight upload admission control (bounds temporary-storage/concurrency).
# ---------------------------------------------------------------------------


def _inflight_config(env_name: str, default: int, error_code: str) -> int:
    raw = _int_env(env_name, str(default))
    if raw <= 0:
        if _current_env_normalized() == "production":
            raise RuntimeError(error_code)
        raw = default
    return raw


def media_inflight_max_per_owner() -> int:
    return _inflight_config(
        "MEDIA_INFLIGHT_MAX_PER_OWNER", 3, "MEDIA_INFLIGHT_MAX_PER_OWNER_REQUIRED_IN_PRODUCTION"
    )


def media_inflight_max_global() -> int:
    return _inflight_config(
        "MEDIA_INFLIGHT_MAX_GLOBAL", 50, "MEDIA_INFLIGHT_MAX_GLOBAL_REQUIRED_IN_PRODUCTION"
    )


def media_inflight_ttl_seconds() -> int:
    return _inflight_config(
        "MEDIA_INFLIGHT_TTL_SECONDS", 300, "MEDIA_INFLIGHT_TTL_SECONDS_REQUIRED_IN_PRODUCTION"
    )


def media_inflight_lock_path() -> Path:
    ensure_media_root()
    return MEDIA_ROOT / ".inflight.lock"


def _reconcile_inflight(db: Session, now: datetime) -> None:
    # Reclaim crash-abandoned reservations by TTL so their slot is freed.
    db.query(MediaUploadReservation).filter(
        MediaUploadReservation.state == "reserved",
        MediaUploadReservation.expires_at < now,
    ).update({MediaUploadReservation.state: "expired"}, synchronize_session=False)
    db.commit()


def reserve_inflight_upload(db: Session, *, owner_user_id: int) -> int:
    """Reserve a persistent in-flight slot BEFORE streaming begins.

    The check-and-insert runs under a shared interprocess lock so concurrent
    uploads across workers cannot exceed the per-owner or global budget (no
    TOCTOU). Expired reservations are reconciled first. Raises 429 when the
    budget is exhausted. Returns the reservation id to be released later.
    """
    with interprocess_file_lock(media_inflight_lock_path()):
        now = datetime.utcnow()
        _reconcile_inflight(db, now)

        active_owner = (
            db.query(func.count(MediaUploadReservation.id))
            .filter(
                MediaUploadReservation.owner_user_id == owner_user_id,
                MediaUploadReservation.state == "reserved",
            )
            .scalar()
            or 0
        )
        if active_owner >= media_inflight_max_per_owner():
            raise HTTPException(status_code=429, detail="media_inflight_limit_owner")

        active_global = (
            db.query(func.count(MediaUploadReservation.id))
            .filter(MediaUploadReservation.state == "reserved")
            .scalar()
            or 0
        )
        if active_global >= media_inflight_max_global():
            raise HTTPException(status_code=429, detail="media_inflight_limit_global")

        reservation = MediaUploadReservation(
            owner_user_id=owner_user_id,
            reserved_bytes=MEDIA_MAX_MB * 1024 * 1024,
            state="reserved",
            expires_at=now + timedelta(seconds=media_inflight_ttl_seconds()),
        )
        db.add(reservation)
        db.commit()
        db.refresh(reservation)
        return reservation.id


def release_inflight_upload(db: Session, reservation_id: int | None) -> None:
    """Release a reservation. Idempotent and never raises: a release failure
    must not mask the primary request's exception (the TTL sweep reclaims the
    slot as a safety net)."""
    if reservation_id is None:
        return
    try:
        with interprocess_file_lock(media_inflight_lock_path()):
            reservation = (
                db.query(MediaUploadReservation)
                .filter(MediaUploadReservation.id == reservation_id)
                .first()
            )
            if reservation is not None and reservation.state == "reserved":
                reservation.state = "released"
                db.add(reservation)
                db.commit()
    except BaseException:
        # Best-effort cleanup: nothing (not even cancellation) may escape and
        # mask the primary request's outcome; the TTL sweep reclaims the slot.
        try:
            db.rollback()
        except BaseException:
            pass


# ---------------------------------------------------------------------------
# Cross-replica coordination gate (fail closed in production).
# ---------------------------------------------------------------------------


def media_upload_coordination_supported() -> bool:
    """Whether a shared, cross-replica transactional coordinator backs the
    in-flight reservation.

    The reservation currently serializes with a host-local interprocess file
    lock, which cannot coordinate uploads across replicas on separate hosts, so
    distributed coordination is NOT available in this build. Enabling it
    requires the shared production database with row/advisory locking (a later
    mission), which is intentionally out of scope here.
    """
    return False


def ensure_media_upload_coordination_supported() -> None:
    """Fail closed in production when cross-replica upload coordination cannot be
    guaranteed — BEFORE any reservation, stream, temporary file or byte exists.

    Dev/test keep using the host-local reservation. Any ambiguity (a detection
    error) fails closed. The raised error is generic and never exposes the
    DATABASE_URL, dialect, host or any internal path.
    """
    if _current_env_normalized() != "production":
        return

    try:
        supported = media_upload_coordination_supported()
    except Exception:
        supported = False

    if not supported:
        raise HTTPException(status_code=503, detail="media_upload_coordination_unavailable")
