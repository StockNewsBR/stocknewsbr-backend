# =====================================================
# STOCKNEWSBR SIGNAL ROUTES
# =====================================================

import logging
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.cache.snapshot_cache import get_snapshot_info, get_snapshot_signals
from app.dependencies import require_channel_access

router = APIRouter(dependencies=[Depends(require_channel_access("app"))])

logger = logging.getLogger("stocknewsbr.routes.signals")


# =====================================================
# GET SIGNALS
# =====================================================

@router.get("/signals")
def get_signals():

    try:

        signals = get_snapshot_signals()
        cache_info = get_snapshot_info()

        return {

            "status": "ok",

            "signals": signals,

            "meta": {

                "total_signals": cache_info.get("signals", 0),
                "cache_age_seconds": cache_info.get("age_seconds"),
                "last_update": cache_info.get("timestamp")

            }

        }

    except Exception as e:

        logger.error(f"Signals route error: {e}")

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )
