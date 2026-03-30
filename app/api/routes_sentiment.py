from fastapi import APIRouter, Depends
from app.dependencies import require_channel_access
from app.social.sentiment_poll import vote, get_sentiment

router = APIRouter(dependencies=[Depends(require_channel_access("app"))])

@router.post("/sentiment/vote")
def sentiment_vote(symbol: str, sentiment: str):

    return vote(symbol, sentiment)

@router.get("/sentiment/{symbol}")
def sentiment(symbol: str):

    return get_sentiment(symbol)
