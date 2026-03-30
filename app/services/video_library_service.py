import json
from pathlib import Path

from app.services.legal_service import HELP_CENTER_MODULES


VIDEO_MANIFEST_PATH = Path("data/help_videos.json")
VIDEO_OUTPUT_DIR = Path("media/help-videos")


def _default_entries():
    entries = []

    for item in HELP_CENTER_MODULES:
        slug = item["slug"]
        filename = f"{slug}.mp4"
        local_path = VIDEO_OUTPUT_DIR / filename
        entries.append(
            {
                "slug": slug,
                "title": item["title"],
                "filename": filename,
                "local_path": str(local_path),
                "public_url": f"/media/help-videos/{filename}" if local_path.exists() else None,
                "status": "available" if local_path.exists() else "planned",
                "script_path": "scripts/generate_help_videos.ps1",
            }
        )

    return entries


def _load_manifest():
    defaults = {item["slug"]: item for item in _default_entries()}

    if not VIDEO_MANIFEST_PATH.exists():
        return defaults

    try:
        payload = json.loads(VIDEO_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return defaults

    if not isinstance(payload, list):
        return defaults

    for item in payload:
        slug = str(item.get("slug") or "").strip()
        if not slug:
            continue
        merged = dict(defaults.get(slug, {}))
        merged.update(item)
        local_path = Path(merged.get("local_path") or (VIDEO_OUTPUT_DIR / f"{slug}.mp4"))
        merged["local_path"] = str(local_path)
        merged["public_url"] = (
            merged.get("public_url")
            or (f"/media/help-videos/{local_path.name}" if local_path.exists() else None)
        )
        merged["status"] = "available" if local_path.exists() else merged.get("status", "planned")
        defaults[slug] = merged

    return defaults


def get_help_video_library():
    entries = list(_load_manifest().values())
    available = sum(1 for item in entries if item.get("status") == "available")

    return {
        "items": entries,
        "status": {
            "interactive_previews_ready": True,
            "mp4_recordings_ready": available == len(entries) and available > 0,
            "available_videos": available,
            "planned_videos": len(entries),
            "next_step": (
                "Instalar ffmpeg e rodar scripts/generate_help_videos.ps1 para renderizar os MP4s."
                if available < len(entries)
                else "Biblioteca de videos pronta para uso."
            ),
        },
    }


def get_help_video_entry(slug: str):
    slug = (slug or "").strip().lower()
    entry = _load_manifest().get(slug)

    if not entry:
        return {
            "slug": slug,
            "status": "missing",
            "video_ready": False,
            "public_url": None,
        }

    return {
        **entry,
        "video_ready": entry.get("status") == "available",
    }
