# =====================================================
# POSTS ENGINE
# =====================================================

import time

from app.social.moderation import can_publish, is_post_hidden
from app.social.store import mutate_social_state, read_social_state


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
    if not user_id or not text:
        return None

    allowed, reason = can_publish(int(user_id), str(text))

    if not allowed:
        return {
            "error": "post_blocked",
            "reason": reason,
        }

    def _create(state):
        counters = state.setdefault("counters", {})
        next_id = int(counters.get("post_id", 0)) + 1
        counters["post_id"] = next_id

        post = {
            "id": next_id,
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

        posts = list(state.get("posts", []))
        posts.append(post)
        state["posts"] = posts[-20000:]
        return post

    return mutate_social_state(_create)


def get_posts(ticker=None, limit=50, blocked_users=None):
    blocked_users = set(blocked_users or [])
    normalized_ticker = ticker.upper() if ticker else None

    def _read(state):
        posts = list(state.get("posts", []))

        if normalized_ticker:
            filtered = [
                post
                for post in posts
                if post.get("ticker") == normalized_ticker
                and post.get("user_id") not in blocked_users
                and not is_post_hidden(post.get("id"))
            ]
            return filtered[-limit:]

        return [
            post
            for post in posts
            if post.get("user_id") not in blocked_users and not is_post_hidden(post.get("id"))
        ][-limit:]

    return read_social_state(_read)


def count_posts(ticker=None):
    def _read(state):
        posts = list(state.get("posts", []))

        if ticker:
            normalized_ticker = ticker.upper()
            return sum(1 for post in posts if post.get("ticker") == normalized_ticker)

        return len(posts)

    return read_social_state(_read)


def get_post(post_id):
    def _read(state):
        for post in reversed(list(state.get("posts", []))):
            if post.get("id") == post_id and not is_post_hidden(post.get("id")):
                return post

        return None

    return read_social_state(_read)


def get_post_ticker(post_id):
    post = get_post(post_id)
    if not post:
        return None
    return post.get("ticker")


def delete_post(post_id, user_id=None):
    existing = get_post(post_id)
    if not existing:
        return False

    if user_id is not None and existing.get("user_id") != user_id:
        return False

    def _delete(state):
        state["posts"] = [post for post in list(state.get("posts", [])) if post.get("id") != post_id]
        return True

    return mutate_social_state(_delete)
