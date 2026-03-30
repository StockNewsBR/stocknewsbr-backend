# =====================================================
# SIGNAL HISTORY STORE
# =====================================================

import time
import threading

MAX_HISTORY = 5000

_lock = threading.Lock()

_signal_history = []


def store_signals(signals):

    if not signals:
        return

    timestamp = int(time.time())

    records = []

    for s in signals:

        record = dict(s)
        record["timestamp"] = timestamp

        records.append(record)

    with _lock:

        _signal_history.extend(records)

        if len(_signal_history) > MAX_HISTORY:

            _signal_history[:] = _signal_history[-MAX_HISTORY:]


def get_history():

    with _lock:

        return list(_signal_history)


def get_top_today():

    now = int(time.time())
    day = 86400

    with _lock:

        today = [
            s for s in _signal_history
            if now - s["timestamp"] < day
        ]

    today.sort(key=lambda x: x["score"], reverse=True)

    return today[:20]


def get_top_week():

    now = int(time.time())
    week = 86400 * 7

    with _lock:

        data = [
            s for s in _signal_history
            if now - s["timestamp"] < week
        ]

    data.sort(key=lambda x: x["score"], reverse=True)

    return data[:20]