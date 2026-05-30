from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import require_any_channel_access
from app.models import User
from app.social.comments import add_comment, get_comments_for_posts
from app.social.followers import get_following_targets
from app.social.likes import get_like_counts, get_liked_post_ids
from app.social.moderation import get_blocked_users
from app.social.reposts import (
    create_repost,
    delete_repost,
    get_repost_counts,
    get_reposted_post_ids,
    get_user_reposts_for_posts,
)
from app.social.posts import create_post, delete_post, get_post, get_posts
from app.services.social_discussion_service import build_discussion_state, rank_featured_discussions
from app.services.social_realtime_service import broadcast_ticker_event


class PostCreateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    image_url: str | None = Field(default=None, max_length=2048)
    sentiment: str | None = Field(default=None, max_length=32)


class CommentCreateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=600)
    image_url: str | None = Field(default=None, max_length=2048)


class RepostCreateRequest(BaseModel):
    quote_text: str | None = Field(default=None, max_length=600)


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
    post_ids = [post.get("id") for post in posts if post.get("id") is not None]
    author_ids = [post.get("user_id") for post in posts if post.get("user_id") is not None]
    comments_by_post = get_comments_for_posts(post_ids, blocked_users=blocked_users)
    like_counts = get_like_counts(post_ids)
    liked_post_ids = get_liked_post_ids(post_ids, current_user.id)
    repost_counts = get_repost_counts(post_ids)
    reposted_post_ids = get_reposted_post_ids(post_ids, current_user.id)
    user_reposts = get_user_reposts_for_posts(post_ids, current_user.id)
    followed_user_ids = get_following_targets(current_user.id, author_ids)

    for post in posts:
        post_id = post.get("id")
        post["comments"] = comments_by_post.get(post_id, [])
        post["likes"] = int(like_counts.get(post_id, 0) or 0)
        post["liked_by_me"] = post_id in liked_post_ids
        post["reposts"] = int(repost_counts.get(post_id, 0) or 0)
        post["reposted_by_me"] = post_id in reposted_post_ids
        user_repost = user_reposts.get(post_id)
        post["my_repost_quote_text"] = user_repost.get("quote_text") if user_repost else None
        post["is_followed_by_me"] = post.get("user_id") in followed_user_ids

    featured_posts = rank_featured_discussions(symbol, posts, limit=min(4, limit))
    discussion_state = build_discussion_state(symbol, posts, featured_posts)

    return {
        "symbol": symbol,
        "count": len(posts),
        "posts": posts,
        "featured_posts": featured_posts,
        "discussion_state": discussion_state,
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


@router.post("/post/{post_id}/repost")
async def repost_post(
    post_id: int,
    payload: RepostCreateRequest | None = None,
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    post = get_post(post_id)

    if not post:
        raise HTTPException(status_code=404, detail="post_not_found")

    repost = create_repost(
        post_id=post_id,
        user_id=current_user.id,
        quote_text=(payload.quote_text if payload else None),
    )

    if not repost:
        raise HTTPException(status_code=400, detail="repost_creation_failed")

    if repost.get("error"):
        raise HTTPException(status_code=429, detail=repost.get("reason", "repost_blocked"))

    await broadcast_ticker_event(
        post.get("ticker"),
        "repost_created",
        {
            "post_id": post_id,
            "repost": repost,
        },
    )
    return {
        "status": "reposted",
        "post_id": post_id,
        "repost": repost,
    }


@router.delete("/post/{post_id}/repost")
async def unrepost_post(
    post_id: int,
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    post = get_post(post_id)

    if not post:
        raise HTTPException(status_code=404, detail="post_not_found")

    if not delete_repost(post_id, current_user.id):
        raise HTTPException(status_code=404, detail="repost_not_found")

    await broadcast_ticker_event(
        post.get("ticker"),
        "repost_deleted",
        {
            "post_id": post_id,
            "user_id": current_user.id,
        },
    )
    return {"status": "unreposted", "post_id": post_id}


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
