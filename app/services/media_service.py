import os
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.services.storage_service import (
    STORAGE_PROVIDER,
    build_public_url,
    build_storage_key,
    create_presigned_upload,
    get_storage_status,
)
from app.system.system_metrics import increment_uploads

MEDIA_ROOT = Path(os.getenv("MEDIA_UPLOAD_DIR", "media")).resolve()
MEDIA_PUBLIC_PREFIX = os.getenv("MEDIA_PUBLIC_PREFIX", "/media").strip() or "/media"
MEDIA_PUBLIC_BASE_URL = os.getenv("MEDIA_PUBLIC_BASE_URL", "").strip()
MEDIA_MAX_MB = max(1, int(os.getenv("MEDIA_MAX_MB", "12")))

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
    content = await file.read()

    max_size_bytes = MEDIA_MAX_MB * 1024 * 1024

    if len(content) > max_size_bytes:
        raise HTTPException(status_code=413, detail="media_too_large")

    destination.write_bytes(content)
    increment_uploads()

    relative_url = f"{MEDIA_PUBLIC_PREFIX.rstrip('/')}/{folder}/{filename}"
    absolute_url = f"{MEDIA_PUBLIC_BASE_URL.rstrip('/')}/{folder}/{filename}" if MEDIA_PUBLIC_BASE_URL else relative_url

    return {
        "provider": STORAGE_PROVIDER,
        "folder": folder,
        "filename": filename,
        "content_type": content_type,
        "size_bytes": len(content),
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
