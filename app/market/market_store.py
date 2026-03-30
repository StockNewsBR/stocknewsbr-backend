# =====================================================
# MARKET STORE
# =====================================================

import threading
import logging

logger = logging.getLogger("stocknewsbr.market.store")


class MarketStore:

    def __init__(self):

        self._pool = {}
        self._lock = threading.RLock()

    def update(self, pool):

        if not pool:
            return

        try:

            with self._lock:
                self._pool = dict(pool)

        except Exception as e:

            logger.error(f"Market store update error: {e}")

    def get(self):

        try:

            with self._lock:
                return dict(self._pool)

        except Exception:

            return {}

    def size(self):

        return len(self._pool)

    def clear(self):

        with self._lock:
            self._pool = {}


market_store = MarketStore()