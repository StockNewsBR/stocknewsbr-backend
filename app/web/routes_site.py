from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.Frontend.marketing_site import get_marketing_site


router = APIRouter(tags=["site"])


@router.get("/site", response_class=HTMLResponse)
def public_site():
    return get_marketing_site()


@router.get("/site/workspace", response_class=HTMLResponse)
def public_workspace_preview():
    return get_marketing_site()
