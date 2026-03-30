# =====================================================
# STOCKNEWSBR TELEGRAM REQUEST
# =====================================================

import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.core.settings import settings

logger = logging.getLogger("stocknewsbr.telegram")

# =====================================================
# SESSION (REUSE CONNECTIONS)
# =====================================================

session = requests.Session()

retry_strategy = Retry(

    total=3,
    backoff_factor=0.5,

    status_forcelist=[
        429,
        500,
        502,
        503,
        504
    ],

    allowed_methods=["POST"]

)

adapter = HTTPAdapter(
    max_retries=retry_strategy,
    pool_connections=5,
    pool_maxsize=5
)

session.mount("https://", adapter)
session.mount("http://", adapter)


# =====================================================
# SEND TELEGRAM MESSAGE
# =====================================================

def send_telegram(url: str, payload: dict) -> bool:

    if not url or not payload:

        logger.warning("Telegram request missing url or payload")

        return False

    try:

        response = session.post(

            url,

            json=payload,

            timeout=(
                settings.TELEGRAM_TIMEOUT,
                settings.TELEGRAM_TIMEOUT
            )

        )

        if response.status_code != 200:

            logger.warning(
                f"Telegram returned status {response.status_code}"
            )

            return False

        return True

    except requests.exceptions.Timeout:

        logger.warning("Telegram timeout")

    except requests.exceptions.ConnectionError:

        logger.warning("Telegram connection error")

    except requests.exceptions.RequestException as e:

        logger.error(f"Telegram request error: {e}")

    except Exception as e:

        logger.error(f"Unexpected telegram error: {e}")

    return False