# =====================================================
# COMMENTS ENGINE
# =====================================================

import time

from app.social.moderation import can_publish

comments = []
_comment_id = 0


def add_comment(post_id, user_id, text, image_url=None, display_name=None, email=None, avatar_url=None):
    global _comment_id

    if post_id is None or not user_id or not text:
        return None

    allowed, reason = can_publish(int(user_id), str(text))

    if not allowed:
        return {
            "error": "comment_blocked",
            "reason": reason,
        }

    _comment_id += 1

    comment = {
        "id": _comment_id,
        "post_id": post_id,
        "user_id": user_id,
        "user": display_name or f"user_{user_id}",
        "user_email": email,
        "user_avatar_url": avatar_url,
        "text": str(text)[:600],
        "image_url": image_url,
        "timestamp": int(time.time()),
    }

    comments.append(comment)

    if len(comments) > 40000:
        comments.pop(0)

    return comment


def get_comments(post_id, blocked_users=None):
    blocked_users = set(blocked_users or [])
    return [
        comment
        for comment in comments
        if comment["post_id"] == post_id and comment.get("user_id") not in blocked_users
    ]


def count_comments(post_ids=None, post_id=None):
    if post_id is not None:
        return sum(1 for comment in comments if comment["post_id"] == post_id)

    if post_ids is not None:
        post_ids = set(post_ids)
        return sum(1 for comment in comments if comment["post_id"] in post_ids)

    return len(comments)
