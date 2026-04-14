from app.social.store import mutate_social_state, read_social_state


def follow(user, target):

    if not user or not target:
        return {"status": "invalid"}

    key = str(target)

    def _follow(state):
        followers = dict(state.get("followers", {}))
        current = set(followers.get(key, set()))
        current.add(user)
        followers[key] = current
        state["followers"] = followers
        return {"status": "following"}

    return mutate_social_state(_follow)


def get_followers(user):
    key = str(user)
    return read_social_state(lambda state: list(set(dict(state.get("followers", {})).get(key, set()))))
