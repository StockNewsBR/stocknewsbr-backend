from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import require_any_channel_access
from app.models import User
from app.social.comments import add_comment, get_comments
from app.social.likes import count_likes, has_liked
from app.social.moderation import get_blocked_users
from app.social.posts import create_post, delete_post, get_post, get_posts
from app.services.social_realtime_service import broadcast_ticker_event


class PostCreateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    image_url: str | None = Field(default=None, max_length=2048)
    sentiment: str | None = Field(default=None, max_length=32)


class CommentCreateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=600)
    image_url: str | None = Field(default=None, max_length=2048)


router = APIRouter(tags=["Social Feed"])


@router.get("/ticker/{symbol}/feed")
def ticker_feed(
    symbol: str,
    limit: int = 30,
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    symbol = symbol.upper()
    blocked_users = get_blocked_users(current_user.id)
    posts = get_posts(symbol, limit, blocked_users=blocked_users)

    for post in posts:
        post_id = post.get("id")
        post["comments"] = get_comments(post_id, blocked_users=blocked_users)
        post["likes"] = count_likes(post_id)
        post["liked_by_me"] = has_liked(post_id, current_user.id)

    return {
        "symbol": symbol,
        "count": len(posts),
        "posts": posts,
    }


@router.post("/ticker/{symbol}/post")
async def create_ticker_post(
    symbol: str,
    payload: PostCreateRequest,
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    post = create_post(
        user_id=current_user.id,
        text=payload.text,
        ticker=symbol,
        image_url=payload.image_url,
        sentiment=payload.sentiment,
        display_name=current_user.display_name or current_user.email,
        email=current_user.email,
        avatar_url=current_user.avatar_url,
    )

    if not post:
        raise HTTPException(status_code=400, detail="post_creation_failed")

    if post.get("error"):
        raise HTTPException(status_code=429, detail=post.get("reason", "post_blocked"))

    await broadcast_ticker_event(
        symbol,
        "post_created",
        {
            "post": post,
        },
    )
    return post


@router.post("/post/{post_id}/comment")
async def create_post_comment(
    post_id: int,
    payload: CommentCreateRequest,
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    post = get_post(post_id)

    if not post:
        raise HTTPException(status_code=404, detail="post_not_found")

    comment = add_comment(
        post_id=post_id,
        user_id=current_user.id,
        text=payload.text,
        image_url=payload.image_url,
        display_name=current_user.display_name or current_user.email,
        email=current_user.email,
        avatar_url=current_user.avatar_url,
    )

    if not comment:
        raise HTTPException(status_code=400, detail="comment_creation_failed")

    if comment.get("error"):
        raise HTTPException(status_code=429, detail=comment.get("reason", "comment_blocked"))

    await broadcast_ticker_event(
        post.get("ticker"),
        "comment_created",
        {
            "post_id": post_id,
            "comment": comment,
        },
    )
    return comment


@router.delete("/post/{post_id}")
async def delete_ticker_post(
    post_id: int,
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    post = get_post(post_id)

    if not post:
        raise HTTPException(status_code=404, detail="post_not_found")

    if not delete_post(post_id, current_user.id):
        raise HTTPException(status_code=403, detail="post_delete_forbidden")

    await broadcast_ticker_event(
        post.get("ticker"),
        "post_deleted",
        {
            "post_id": post_id,
        },
    )
    return {"status": "deleted", "post_id": post_id}
