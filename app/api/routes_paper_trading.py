from fastapi import APIRouter, Depends

from app.dependencies import require_internal_token
from app.system.paper_trading import get_paper_trading_status, summarize_paper_trading_status
from app.system.signal_outcome_audit import get_signal_outcome_audit_status

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


@router.get("/outcomes")
def internal_signal_outcome_audit_status():
    payload = get_signal_outcome_audit_status()
    return {
        "mode": payload.get("mode"),
        "simulation": payload.get("simulation"),
        "paper_only": True,
        "signal_outcome_status": payload.get("signal_outcome_status"),
        "windows_seconds": payload.get("windows_seconds", {}),
        "metrics": payload.get("metrics", {}),
        "records": payload.get("records", []),
    }
