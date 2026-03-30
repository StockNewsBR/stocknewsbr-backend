from fastapi import APIRouter, Depends

from app.dependencies import require_any_channel_access
from app.models import User
from app.social.moderation import get_blocked_users
from app.social.posts import get_posts

router = APIRouter(tags=["Social"])


@router.get("/social/posts")
def social_posts(
    limit: int = 50,
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    blocked_users = get_blocked_users(current_user.id)
    return {
        "posts": get_posts(limit=limit, blocked_users=blocked_users),
    }
