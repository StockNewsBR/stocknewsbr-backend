# =====================================================
# STOCKNEWSBR WEB TERMINAL ROUTES
# =====================================================

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
import logging

from app.cache.snapshot_cache import get_snapshot
from app.dependencies import require_channel_access
from app.Frontend.trader_terminal import get_terminal as render_terminal_html
from app.services.ranking import get_ranking

router = APIRouter(
    prefix="/web",
    tags=["web"],
    dependencies=[Depends(require_channel_access("web"))],
)

logger = logging.getLogger("stocknewsbr.web.terminal")


# =====================================================
# TERMINAL DATA
# =====================================================

@router.get("/terminal")
def get_terminal():

    try:

        snapshot = get_snapshot()

        ranking = get_ranking()

        return {

            "snapshot": snapshot,
            "ranking": ranking

        }

    except Exception as e:

        logger.error(f"Terminal route error: {e}")

        return {

            "snapshot": {},
            "ranking": []

        }


@router.get("/terminal/ui", response_class=HTMLResponse)
def terminal_ui(token: str | None = Query(default=None)):
    return render_terminal_html(token=token)


@router.get("/terminal/popout/{tab_id}", response_class=HTMLResponse)
def terminal_popout(
    tab_id: str,
    token: str | None = Query(default=None),
):
    return render_terminal_html(focused_tab=tab_id, token=token)
