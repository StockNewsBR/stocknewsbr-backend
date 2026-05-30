from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import require_any_channel_access
from app.models import User
from app.services.poll_service import get_poll_history, get_poll_report, get_weekly_poll, vote_poll

router = APIRouter(
    prefix="/poll",
    tags=["Polls"],
)


@router.get("/{symbol}")
def poll_detail(symbol: str):
    return get_weekly_poll(symbol)


@router.get("/{symbol}/history")
def poll_history(symbol: str, limit: int = 8):
    return {
        "symbol": symbol.upper(),
        "history": get_poll_history(symbol, limit=limit),
    }


@router.get("/{symbol}/report")
def poll_report(symbol: str):
    return {
        "symbol": symbol.upper(),
        "report": get_poll_report(symbol),
    }


@router.post("/{symbol}/vote")
def vote(
    symbol: str,
    option: str,
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    try:
        poll = vote_poll(symbol=symbol, option_key=option, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return poll
