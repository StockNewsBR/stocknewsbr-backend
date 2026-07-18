from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx


TENOR_SEARCH_URL = "https://tenor.googleapis.com/v2/search"
TENOR_MEDIA_HOST = "media.tenor.com"


def is_approved_gif_url(value: str | None) -> bool:
    try:
        parsed = urlparse(str(value or "").strip())
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname == TENOR_MEDIA_HOST and bool(parsed.path)


def search_tenor_gifs(query: str, *, locale: str = "pt-BR", limit: int = 12) -> dict:
    normalized_query = " ".join(str(query or "").split())[:120]
    if not normalized_query:
        return {"status": "EMPTY", "query": "", "items": [], "reason": "query_required"}

    api_key = os.getenv("TENOR_API_KEY", "").strip()
    if not api_key:
        return {
            "status": "UNAVAILABLE",
            "query": normalized_query,
            "items": [],
            "reason": "tenor_api_key_not_configured",
        }

    safe_limit = max(1, min(int(limit), 24))
    try:
        response = httpx.get(
            TENOR_SEARCH_URL,
            params={
                "key": api_key,
                "q": normalized_query,
                "limit": safe_limit,
                "locale": "en_US" if locale == "en-US" else "pt_BR",
                "contentfilter": "medium",
                "media_filter": "gif,tinygif",
            },
            timeout=8.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        return {"status": "ERROR", "query": normalized_query, "items": [], "reason": "provider_request_failed"}

    if not isinstance(payload, dict):
        return {"status": "ERROR", "query": normalized_query, "items": [], "reason": "invalid_provider_payload"}

    items = []
    for result in payload.get("results", []):
        formats = result.get("media_formats") or {}
        media = formats.get("gif") or {}
        preview = formats.get("tinygif") or media
        media_url = str(media.get("url") or "")
        preview_url = str(preview.get("url") or media_url)
        if not is_approved_gif_url(media_url) or not is_approved_gif_url(preview_url):
            continue
        dims = media.get("dims") or []
        items.append(
            {
                "id": str(result.get("id") or ""),
                "title": str(result.get("content_description") or normalized_query)[:200],
                "preview_url": preview_url,
                "media_url": media_url,
                "width": dims[0] if len(dims) > 0 else None,
                "height": dims[1] if len(dims) > 1 else None,
                "provider": "tenor",
            }
        )

    return {
        "status": "READY" if items else "EMPTY",
        "query": normalized_query,
        "items": items,
        "reason": None if items else "no_safe_results",
    }
