from fastapi import APIRouter, Depends

from app.dependencies import require_internal_token
from app.system.explainability import get_explainability_status

router = APIRouter(
    prefix="/internal",
    tags=["Internal Explainability"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("/explainability")
def internal_explainability_status():
    return get_explainability_status()
