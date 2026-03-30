import datetime

def is_market_active(symbol):

    now = datetime.datetime.utcnow()

    hour = now.hour

    # Crypto sempre ativo
    if symbol.endswith("-USD"):
        return True

    # B3
    if symbol.endswith(".SA"):

        if 13 <= hour <= 21:
            return True

        return False

    # US
    if not symbol.endswith(".SA"):

        if 14 <= hour <= 21:
            return True

        return False

    return False