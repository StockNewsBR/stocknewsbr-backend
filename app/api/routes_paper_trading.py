from fastapi import APIRouter, Depends

from app.dependencies import require_internal_token
from app.system.paper_trading import get_paper_trading_status, summarize_paper_trading_status

router = APIRouter(
    prefix="/internal/paper-trading",
    tags=["Internal Paper Trading"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("")
def internal_paper_trading_status():
    payload = get_paper_trading_status()
    return {
        **summarize_paper_trading_status(payload),
        "paper_only": True,
        "positions": payload.get("positions", []),
        "trades": payload.get("trades", []),
        "skipped": payload.get("skipped", []),
        "metrics": payload.get("metrics", {}),
    }
