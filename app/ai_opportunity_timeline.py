import time

timeline = {}

def register_signal(symbol):

    now = int(time.time())

    timeline[symbol] = now

def get_signal_age(symbol):

    if symbol not in timeline:
        return None

    age = int(time.time()) - timeline[symbol]

    return age