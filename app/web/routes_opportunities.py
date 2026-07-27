# =====================================================
# STOCKNEWSBR OPPORTUNITIES ROUTES
# =====================================================

from fastapi import APIRouter, Depends
import logging

from app.dependencies import require_channel_access
from app.services.ranking import get_ranking

router = APIRouter(
    prefix="/web",
    tags=["web"],
    dependencies=[Depends(require_channel_access("web"))],
)

logger = logging.getLogger("stocknewsbr.web.opportunities")


# =====================================================
# TOP OPPORTUNITIES
# =====================================================

@router.get("/opportunities")
def get_opportunities():

    try:

        return get_ranking()[:25]

    except Exception as e:

        logger.error("Opportunities route error: %s", e)

        return []
