from app.social.store import mutate_social_state, read_social_state


def like_post(post_id, user_id):
    if post_id is None or not user_id:
        return 0

    key = str(post_id)

    def _like(state):
        likes = dict(state.get("likes", {}))
        liked_users = set(likes.get(key, set()))
        liked_users.add(user_id)
        likes[key] = liked_users
        state["likes"] = likes
        return len(liked_users)

    return mutate_social_state(_like)


def unlike_post(post_id, user_id):
    key = str(post_id)

    def _unlike(state):
        likes = dict(state.get("likes", {}))
        liked_users = set(likes.get(key, set()))
        liked_users.discard(user_id)
        likes[key] = liked_users
        state["likes"] = likes
        return len(liked_users)

    return mutate_social_state(_unlike)


def count_likes(post_id):
    key = str(post_id)
    return read_social_state(lambda state: len(set(dict(state.get("likes", {})).get(key, set()))))


def has_liked(post_id, user_id):

    if post_id is None or not user_id:
        return False

    key = str(post_id)
    return read_social_state(lambda state: user_id in set(dict(state.get("likes", {})).get(key, set())))
