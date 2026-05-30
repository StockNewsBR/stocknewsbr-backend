from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import require_any_channel_access
from app.services.quote_service import get_cached_quote_payload

router = APIRouter(dependencies=[Depends(require_any_channel_access("app", "web"))])

@router.get("/ticker/{symbol}")
def ticker(symbol: str):

    symbol = symbol.upper().strip()

    data = get_cached_quote_payload(symbol)

    if not data:
        raise HTTPException(
            status_code=404,
            detail="Ticker not found"
        )

    return {
        "symbol": symbol,
        "price": data.get("price"),
        "change": data.get("change"),
        "change_pct": data.get("change_pct"),
        "after_hours": data.get("after_hours"),
        "pre_market": data.get("pre_market"),
        "volume": data.get("volume"),
        "high": data.get("high"),
        "low": data.get("low")
    }
