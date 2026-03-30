# =====================================================
# FOLLOWERS ENGINE
# =====================================================

followers = {}


def follow(user, target):

    if not user or not target:
        return {"status": "invalid"}

    followers.setdefault(target, set())
    followers[target].add(user)

    return {"status": "following"}


def get_followers(user):

    return list(followers.get(user, []))