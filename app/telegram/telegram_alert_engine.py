# =====================================================
# STOCKNEWSBR TELEGRAM ALERT ENGINE
# =====================================================

import os
import time
import logging
import threading
import requests

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.telegram.telegram_alert_formatter import format_signal_alert

logger = logging.getLogger("stocknewsbr.telegram")

# =====================================================
# CONFIG
# =====================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_URL = "https://api.telegram.org/bot"

TIMEOUT = (3, 6)

MIN_ALERT_INTERVAL = 1

MAX_SENT_CACHE = 500

# =====================================================
# STATE
# =====================================================

_last_alert_time = 0

_lock = threading.Lock()

_sent_signals = set()

# =====================================================
# HTTP SESSION
# =====================================================

_session = requests.Session()

retry = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["POST"]
)

adapter = HTTPAdapter(
    pool_connections=10,
    pool_maxsize=10,
    max_retries=retry
)

_session.mount("https://", adapter)
_session.mount("http://", adapter)

# =====================================================
# SEND MESSAGE
# =====================================================

def send_alert(message: str) -> bool:

    global _last_alert_time

    if not TELEGRAM_TOKEN or not CHAT_ID:

        logger.warning("Telegram token or chat_id not configured")

        return False

    try:

        with _lock:

            now = time.time()

            if now - _last_alert_time < MIN_ALERT_INTERVAL:
                return False

            _last_alert_time = now

        url = f"{BASE_URL}{TELEGRAM_TOKEN}/sendMessage"

        payload = {

            "chat_id": CHAT_ID,
            "text": message[:4000],
            "parse_mode": "Markdown"

        }

        r = _session.post(
            url,
            json=payload,
            timeout=TIMEOUT
        )

        if r.status_code != 200:

            logger.warning(f"Telegram status {r.status_code}")

            return False

        return True

    except Exception as e:

        logger.error(f"Telegram send error: {e}")

        return False

# =====================================================
# SIGNAL ALERT
# =====================================================

def send_signal_alert(signal: dict, regime=None):

    try:

        if not isinstance(signal, dict):
            return

        ticker = signal.get("ticker")

        if not ticker:
            return

        with _lock:

            if ticker in _sent_signals:
                return

            _sent_signals.add(ticker)

            if len(_sent_signals) > MAX_SENT_CACHE:
                _sent_signals.clear()

        message = format_signal_alert(signal, regime)

        send_alert(message)

    except Exception as e:

        logger.error(f"Signal alert error: {e}")

# =====================================================
# BULK ALERT
# =====================================================

def send_bulk_alert(signals, regime=None):

    if not signals:
        return

    try:

        for s in signals:

            if not isinstance(s, dict):
                continue

            score = s.get("score")

            if not isinstance(score, (int, float)):
                continue

            if score >= 85:

                send_signal_alert(s, regime)

    except Exception as e:

        logger.error(f"Bulk alert error: {e}")