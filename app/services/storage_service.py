import os
from pathlib import Path
from uuid import uuid4


try:
    import boto3
except Exception:  # pragma: no cover - optional dependency
    boto3 = None


STORAGE_PROVIDER = os.getenv("STORAGE_PROVIDER", "local").strip().lower()
STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "").strip()
STORAGE_REGION = os.getenv("STORAGE_REGION", "auto").strip()
STORAGE_ENDPOINT_URL = os.getenv("STORAGE_ENDPOINT_URL", "").strip() or None
STORAGE_ACCESS_KEY_ID = os.getenv("STORAGE_ACCESS_KEY_ID", "").strip()
STORAGE_SECRET_ACCESS_KEY = os.getenv("STORAGE_SECRET_ACCESS_KEY", "").strip()
STORAGE_PUBLIC_BASE_URL = os.getenv("STORAGE_PUBLIC_BASE_URL", "").strip()
LOCAL_MEDIA_ROOT = Path(os.getenv("MEDIA_UPLOAD_DIR", "media")).resolve()
SIGNED_UPLOAD_EXPIRES = max(60, int(os.getenv("SIGNED_UPLOAD_EXPIRES", "900")))


def _is_s3_provider():
    return STORAGE_PROVIDER in {"s3", "r2", "cloudflare_r2"}


def _client():
    if not _is_s3_provider() or boto3 is None:
        return None

    if not STORAGE_BUCKET or not STORAGE_ACCESS_KEY_ID or not STORAGE_SECRET_ACCESS_KEY:
        return None

    session = boto3.session.Session()
    return session.client(
        "s3",
        region_name=STORAGE_REGION,
        endpoint_url=STORAGE_ENDPOINT_URL,
        aws_access_key_id=STORAGE_ACCESS_KEY_ID,
        aws_secret_access_key=STORAGE_SECRET_ACCESS_KEY,
    )


def get_storage_status():
    provider_ready = False
    mode = "local"

    if _is_s3_provider():
        mode = STORAGE_PROVIDER
        provider_ready = _client() is not None
    else:
        LOCAL_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
        provider_ready = LOCAL_MEDIA_ROOT.exists()

    return {
        "provider": mode,
        "ready": provider_ready,
        "bucket": STORAGE_BUCKET or None,
        "endpoint_url": STORAGE_ENDPOINT_URL,
        "public_base_url": STORAGE_PUBLIC_BASE_URL or None,
        "signed_upload_supported": _is_s3_provider() and provider_ready,
        "next_step": (
            "Configurar bucket, chaves e endpoint S3/R2 para upload assinado."
            if not provider_ready and _is_s3_provider()
            else "Storage local pronto; para CDN real configure S3/R2."
        ),
    }


def build_storage_key(folder: str, extension: str):
    folder = (folder or "posts").strip("/").replace("\\", "/")
    extension = extension if extension.startswith(".") else f".{extension}"
    return f"{folder}/{uuid4().hex}{extension}"


def build_public_url(key: str):
    if STORAGE_PUBLIC_BASE_URL:
        return f"{STORAGE_PUBLIC_BASE_URL.rstrip('/')}/{key}"

    return f"/media/{key}"


def create_presigned_upload(folder: str, extension: str, content_type: str):
    client = _client()

    if client is None:
        return None

    key = build_storage_key(folder, extension)
    params = {
        "Bucket": STORAGE_BUCKET,
        "Key": key,
        "ContentType": content_type,
    }
    upload_url = client.generate_presigned_url(
        "put_object",
        Params=params,
        ExpiresIn=SIGNED_UPLOAD_EXPIRES,
    )

    return {
        "provider": STORAGE_PROVIDER,
        "bucket": STORAGE_BUCKET,
        "key": key,
        "upload_url": upload_url,
        "public_url": build_public_url(key),
        "expires_in": SIGNED_UPLOAD_EXPIRES,
    }
