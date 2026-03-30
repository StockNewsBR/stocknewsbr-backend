from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends

from app.dependencies import require_internal_token
from app.social.moderation import get_moderation_summary, get_review_queue, review_report


class ReviewReportRequest(BaseModel):
    post_id: int
    action: str = Field(..., min_length=2, max_length=32)
    moderator_id: int | None = None


router = APIRouter(
    prefix="/moderation/admin",
    tags=["Moderation Admin"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("/review-queue")
def moderation_review_queue(limit: int = 100):
    return {"items": get_review_queue(limit=limit)}


@router.post("/review")
def moderation_review(payload: ReviewReportRequest):
    return review_report(
        post_id=payload.post_id,
        action=payload.action,
        moderator_id=payload.moderator_id,
    )


@router.get("/summary")
def moderation_summary():
    return get_moderation_summary()
