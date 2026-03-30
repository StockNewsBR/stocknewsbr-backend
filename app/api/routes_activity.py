from fastapi import APIRouter, Depends

from app.dependencies import require_any_channel_access
from app.models import User
from app.social.comments import count_comments
from app.social.moderation import get_blocked_users
from app.social.posts import get_posts

router = APIRouter(tags=["Activity"])


@router.get("/ticker/{symbol}/activity")
def activity(
    symbol: str,
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    symbol = symbol.upper()
    blocked_users = get_blocked_users(current_user.id)
    posts = get_posts(symbol, limit=500, blocked_users=blocked_users)
    post_ids = [post["id"] for post in posts]
    post_count = len(posts)
    comment_count = count_comments(post_ids=post_ids)

    return {
        "symbol": symbol,
        "posts": post_count,
        "comments": comment_count,
        "message_volume": post_count + comment_count,
    }
