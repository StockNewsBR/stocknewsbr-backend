# =====================================================
# COMMENTS ENGINE
# =====================================================

import time

from app.social.moderation import can_publish
from app.social.store import mutate_social_state, read_social_state


def add_comment(post_id, user_id, text, image_url=None, display_name=None, email=None, avatar_url=None):
    if post_id is None or not user_id or not text:
        return None

    allowed, reason = can_publish(int(user_id), str(text))

    if not allowed:
        return {
            "error": "comment_blocked",
            "reason": reason,
        }

    def _create(state):
        counters = state.setdefault("counters", {})
        next_id = int(counters.get("comment_id", 0)) + 1
        counters["comment_id"] = next_id

        comment = {
            "id": next_id,
            "post_id": post_id,
            "user_id": user_id,
            "user": display_name or f"user_{user_id}",
            "user_email": email,
            "user_avatar_url": avatar_url,
            "text": str(text)[:600],
            "image_url": image_url,
            "timestamp": int(time.time()),
        }

        comments = list(state.get("comments", []))
        comments.append(comment)
        state["comments"] = comments[-40000:]
        return comment

    return mutate_social_state(_create)


def get_comments(post_id, blocked_users=None):
    blocked_users = set(blocked_users or [])

    def _read(state):
        return [
            comment
            for comment in list(state.get("comments", []))
            if comment["post_id"] == post_id and comment.get("user_id") not in blocked_users
        ]

    return read_social_state(_read)


def count_comments(post_ids=None, post_id=None):
    def _read(state):
        comments = list(state.get("comments", []))

        if post_id is not None:
            return sum(1 for comment in comments if comment["post_id"] == post_id)

        if post_ids is not None:
            lookup = set(post_ids)
            return sum(1 for comment in comments if comment["post_id"] in lookup)

        return len(comments)

    return read_social_state(_read)
