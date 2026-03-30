from sqlalchemy.orm import Session

from app.models import MediaAsset


def create_media_asset(
    db: Session,
    *,
    owner_user_id: int,
    provider: str,
    folder: str,
    filename: str,
    storage_key: str | None = None,
    content_type: str | None = None,
    size_bytes: int | None = None,
    public_url: str | None = None,
    status: str = "uploaded",
):
    asset = MediaAsset(
        owner_user_id=owner_user_id,
        provider=provider,
        folder=folder,
        filename=filename,
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=size_bytes,
        public_url=public_url,
        status=status,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def serialize_media_asset(asset: MediaAsset):
    return {
        "id": asset.id,
        "owner_user_id": asset.owner_user_id,
        "provider": asset.provider,
        "folder": asset.folder,
        "filename": asset.filename,
        "storage_key": asset.storage_key,
        "content_type": asset.content_type,
        "size_bytes": asset.size_bytes,
        "public_url": asset.public_url,
        "status": asset.status,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }


def get_media_asset(db: Session, asset_id: int):
    return db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
