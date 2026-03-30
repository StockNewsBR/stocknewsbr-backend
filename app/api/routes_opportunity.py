from fastapi import APIRouter, Depends
from app.dependencies import require_channel_access
from app.ai.opportunity_spotlight import get_best_opportunity

router = APIRouter(dependencies=[Depends(require_channel_access("app"))])


@router.get("/market/opportunity")
def opportunity():

    opp = get_best_opportunity()

    if not opp:
        return {
            "status": "no opportunity"
        }

    return {
        "type": "OPPORTUNITY_SPOTLIGHT",
        "data": opp
    }
