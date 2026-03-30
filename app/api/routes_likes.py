from fastapi import APIRouter, Depends

from app.dependencies import require_any_channel_access
from app.models import User
from app.social.likes import like_post, unlike_post
from app.social.posts import get_post
from app.services.social_realtime_service import broadcast_ticker_event

router = APIRouter(tags=["Likes"])


@router.post("/post/{post_id}/like")
async def like(
    post_id: int,
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    post = get_post(post_id)
    like_count = like_post(post_id, current_user.id)

    await broadcast_ticker_event(
        post.get("ticker") if post else None,
        "like_added",
        {
            "post_id": post_id,
            "likes": like_count,
            "user_id": current_user.id,
        },
    )
    return {"likes": like_count}


@router.post("/post/{post_id}/unlike")
async def unlike(
    post_id: int,
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    post = get_post(post_id)
    like_count = unlike_post(post_id, current_user.id)

    await broadcast_ticker_event(
        post.get("ticker") if post else None,
        "like_removed",
        {
            "post_id": post_id,
            "likes": like_count,
            "user_id": current_user.id,
        },
    )
    return {"likes": like_count}
