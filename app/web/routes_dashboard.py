# =====================================================
# STOCKNEWSBR DASHBOARD ROUTES
# =====================================================

from fastapi import APIRouter, Depends
import logging

from app.dependencies import require_channel_access
from app.system.system_metrics import get_metrics_snapshot

router = APIRouter(
    prefix="/web",
    tags=["web"],
    dependencies=[Depends(require_channel_access("web"))],
)

logger = logging.getLogger("stocknewsbr.web.dashboard")


# =====================================================
# DASHBOARD
# =====================================================

@router.get("/dashboard")
def dashboard():

    try:
        metrics = get_metrics_snapshot()

        return {
            "engine_cycles": metrics["engine_cycles"],
            "scan_time": metrics["scan_time"],
            "signals_generated": metrics["signals_generated"],
            "cache_age": metrics["cache_age"],
        }

    except Exception as e:

        logger.error(f"Dashboard route error: {e}")

        return {}
