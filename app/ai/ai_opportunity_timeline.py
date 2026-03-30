# =====================================================
# STOCKNEWSBR OPPORTUNITY TIMELINE
# Thread Safe + Fast
# =====================================================

import time
import threading
import logging
from datetime import datetime

logger = logging.getLogger("stocknewsbr.opportunity_timeline")

timeline = {}
lock = threading.Lock()

MAX_TRACKED = 500


def register_signal(symbol):

    if not symbol:
        return

    now = int(time.time())

    try:

        with lock:

            timeline[symbol] = now

            if len(timeline) > MAX_TRACKED:

                oldest = min(timeline.items(), key=lambda x: x[1])[0]
                timeline.pop(oldest, None)

    except Exception:

        logger.exception("Register signal error")


def get_signal_age(symbol):

    if not symbol:
        return None

    try:

        with lock:

            ts = timeline.get(symbol)

        if not ts:
            return None

        return int(time.time()) - ts

    except Exception:

        logger.exception("Signal age error")

        return None


def opportunity_spotlight():

    try:

        with lock:

            if not timeline:

                return {
                    "spotlight": None,
                    "message": "No signals registered yet"
                }

            symbol, ts = max(
                timeline.items(),
                key=lambda x: x[1]
            )

        age = int(time.time()) - ts

        return {

            "ticker": symbol,
            "signal_age_seconds": age,
            "timestamp": datetime.utcnow().isoformat(),
            "type": "Opportunity Spotlight"

        }

    except Exception:

        logger.exception("Opportunity spotlight error")

        return {

            "spotlight": None,
            "message": "Spotlight unavailable"
        }