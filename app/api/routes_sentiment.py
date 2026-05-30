from fastapi import APIRouter, Depends

from app.dependencies import require_channel_access
from app.models import User
from app.social.sentiment_poll import vote, get_sentiment

router = APIRouter(dependencies=[Depends(require_channel_access("app"))])


@router.post("/sentiment/vote")
def sentiment_vote(
    symbol: str,
    sentiment: str,
    current_user: User = Depends(require_channel_access("app")),
):
    return vote(symbol, sentiment, user_id=current_user.id)


@router.get("/sentiment/{symbol}")
def sentiment(symbol: str):
    return get_sentiment(symbol)
