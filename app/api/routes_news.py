from fastapi import APIRouter, Depends

from app.dependencies import require_any_channel_access
from app.models import User
from app.services.public_news_service import build_public_news_payload


router = APIRouter(tags=["News"])


@router.get("/news/{symbol}")
def symbol_news(
    symbol: str,
    limit: int = 6,
    refresh: str | None = None,
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    del current_user
    # Cache-first: the HTTP path never calls the provider synchronously. A
    # refresh request schedules a bounded, deduplicated background warmup
    # (see news_warmup) instead of blocking the request on a provider fetch.
    return build_public_news_payload(
        symbol,
        limit=limit,
        allow_fetch=False,
        schedule_warmup=True,
    )
