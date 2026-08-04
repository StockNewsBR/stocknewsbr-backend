# =====================================================
# STOCKNEWSBR WEB TERMINAL ROUTES
# =====================================================

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse
import logging

from app.cache.snapshot_cache import get_snapshot
from app.dependencies import require_channel_access
from app.Frontend.trader_terminal import get_terminal as render_terminal_html
from app.models import User
from app.services.browser_ticket_service import consume_browser_ticket, issue_browser_ticket
from app.services.ranking import get_ranking

router = APIRouter(
    prefix="/web",
    tags=["web"],
    dependencies=[Depends(require_channel_access("web"))],
)

logger = logging.getLogger("stocknewsbr.web.terminal")


class BrowserTicketRequest(BaseModel):
    scope: str = Field(pattern="^(popout|chat)$")
    target: str = Field(min_length=1, max_length=32)


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

        logger.error("Terminal route error: %s", e)

        return {

            "snapshot": {},
            "ranking": []

        }


@router.get("/terminal/ui", response_class=HTMLResponse)
def terminal_ui(token: str | None = Query(default=None)):
    return render_terminal_html(token=token)


@router.post("/terminal/ticket")
def terminal_ticket(
    payload: BrowserTicketRequest,
    current_user: User = Depends(require_channel_access("web")),
):
    ticket = issue_browser_ticket(
        user_id=current_user.id,
        display_name=current_user.display_name or current_user.email,
        scope=payload.scope,
        target=payload.target,
    )
    return {"ticket": ticket, "expires_in": 30}


@router.post("/terminal/popout/{tab_id}", response_class=HTMLResponse)
def terminal_popout(
    tab_id: str,
    ticket: str = Form(...),
    current_user: User = Depends(require_channel_access("web")),
):
    payload = consume_browser_ticket(ticket, scope="popout", target=tab_id)
    if not payload or payload["user_id"] != current_user.id:
        raise HTTPException(status_code=401, detail="invalid_browser_ticket")
    return render_terminal_html(focused_tab=tab_id)
