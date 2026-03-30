# =====================================================
# LIKES ENGINE
# =====================================================

likes = {}


def like_post(post_id, user_id):

    if post_id is None or not user_id:
        return 0

    likes.setdefault(post_id, set())
    likes[post_id].add(user_id)

    return len(likes[post_id])


def unlike_post(post_id, user_id):

    if post_id in likes:
        likes[post_id].discard(user_id)

    return len(likes.get(post_id, []))


def count_likes(post_id):

    return len(likes.get(post_id, []))


def has_liked(post_id, user_id):

    if post_id is None or not user_id:
        return False

    return user_id in likes.get(post_id, set())
