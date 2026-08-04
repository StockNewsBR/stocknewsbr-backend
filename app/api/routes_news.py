from fastapi import APIRouter, Depends

from app.dependencies import require_any_channel_access
from app.models import User
from app.services.public_news_service import build_public_news_payload


router = APIRouter(tags=["News"])


@router.get("/news/{symbol}")
def symbol_news(
    symbol: str,
    limit: int = 6,
    refresh: bool = False,
    locale: str = "pt-BR",
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    del current_user
    kwargs = {"limit": limit, "allow_fetch": False, "schedule_warmup": refresh}
    if locale != "pt-BR":
        kwargs["locale"] = locale
    return build_public_news_payload(symbol, **kwargs)
