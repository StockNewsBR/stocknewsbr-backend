# =====================================================
# POSTS ENGINE
# =====================================================

import time

from app.social.moderation import can_publish, is_post_hidden

posts = []
_post_id = 0


def create_post(
    user_id,
    text,
    ticker=None,
    image_url=None,
    sentiment=None,
    display_name=None,
    email=None,
    avatar_url=None,
):
    global _post_id

    if not user_id or not text:
        return None

    allowed, reason = can_publish(int(user_id), str(text))

    if not allowed:
        return {
            "error": "post_blocked",
            "reason": reason,
        }

    _post_id += 1

    post = {
        "id": _post_id,
        "user_id": user_id,
        "user": display_name or f"user_{user_id}",
        "user_email": email,
        "user_avatar_url": avatar_url,
        "text": str(text)[:1000],
        "ticker": ticker.upper() if ticker else None,
        "image_url": image_url,
        "sentiment": sentiment,
        "timestamp": int(time.time()),
    }

    posts.append(post)

    if len(posts) > 20000:
        posts.pop(0)

    return post


def get_posts(ticker=None, limit=50, blocked_users=None):
    blocked_users = set(blocked_users or [])

    if ticker:
        filtered = [
            post
            for post in posts
            if post.get("ticker") == ticker
            and post.get("user_id") not in blocked_users
            and not is_post_hidden(post.get("id"))
        ]
        return filtered[-limit:]

    return [
        post
        for post in posts
        if post.get("user_id") not in blocked_users and not is_post_hidden(post.get("id"))
    ][-limit:]


def count_posts(ticker=None):
    if ticker:
        ticker = ticker.upper()
        return sum(1 for post in posts if post.get("ticker") == ticker)

    return len(posts)


def get_post(post_id):
    for post in reversed(posts):
        if post.get("id") == post_id and not is_post_hidden(post.get("id")):
            return post

    return None


def get_post_ticker(post_id):
    post = get_post(post_id)
    if not post:
        return None
    return post.get("ticker")


def delete_post(post_id, user_id=None):
    global posts

    existing = get_post(post_id)
    if not existing:
        return False

    if user_id is not None and existing.get("user_id") != user_id:
        return False

    posts = [post for post in posts if post.get("id") != post_id]
    return True
