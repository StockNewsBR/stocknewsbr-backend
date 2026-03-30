# =====================================================
# STOCKNEWSBR MARKET API
# =====================================================

from fastapi import APIRouter, Depends
from app.dependencies import require_channel_access
from app.cache.snapshot_cache import get_snapshot

router = APIRouter(dependencies=[Depends(require_channel_access("app"))])


# -----------------------------------------------------
# FULL SNAPSHOT
# -----------------------------------------------------

@router.get("/snapshot")

def snapshot():

    return get_snapshot()


# -----------------------------------------------------
# MARKET STORY
# -----------------------------------------------------

@router.get("/market-story")

def market_story():

    snapshot = get_snapshot()

    return {
        "market_story": snapshot.get("market_story")
    }


# -----------------------------------------------------
# MARKET REGIME
# -----------------------------------------------------

@router.get("/market-regime")

def market_regime():

    snapshot = get_snapshot()

    return {
        "market_regime": snapshot.get("market_regime")
    }


# -----------------------------------------------------
# SECTOR ROTATION
# -----------------------------------------------------

@router.get("/sector-rotation")

def sector_rotation():

    snapshot = get_snapshot()

    return {
        "sector_rotation": snapshot.get("sector_rotation")
    }


# -----------------------------------------------------
# TOP SIGNALS
# -----------------------------------------------------

@router.get("/top-signals")

def top_signals():

    snapshot = get_snapshot()

    signals = snapshot.get("signals", [])

    return {
        "signals": signals[:10]
    }


# -----------------------------------------------------
# SYSTEM HEALTH
# -----------------------------------------------------

@router.get("/system-health")

def system_health():

    snapshot = get_snapshot()

    return {
        "status": "running",
        "signals": len(snapshot.get("signals", []))
    }
