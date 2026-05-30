from fastapi import APIRouter, Depends

from app.dependencies import require_any_channel_access
from app.models import User
from app.social.followers import follow as follow_user
from app.social.followers import is_following, unfollow as unfollow_user
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


@router.post("/social/users/{target_user_id}/follow")
def follow_social_user(
    target_user_id: int,
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    result = follow_user(current_user.id, target_user_id)
    return {
        "status": result.get("status", "unknown"),
        "is_following": is_following(current_user.id, target_user_id),
    }


@router.delete("/social/users/{target_user_id}/follow")
def unfollow_social_user(
    target_user_id: int,
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    result = unfollow_user(current_user.id, target_user_id)
    return {
        "status": result.get("status", "unknown"),
        "is_following": is_following(current_user.id, target_user_id),
    }
