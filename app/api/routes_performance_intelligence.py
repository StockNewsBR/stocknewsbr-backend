from fastapi import APIRouter, Depends

from app.dependencies import require_internal_token
from app.system.performance_intelligence import get_performance_intelligence_status

router = APIRouter(
    prefix="/internal",
    tags=["Internal Performance Intelligence"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("/performance-intelligence")
def internal_performance_intelligence_status():
    return get_performance_intelligence_status()
