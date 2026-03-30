# =====================================================
# SAFE API REQUEST
# =====================================================

import logging
import requests

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.core.settings import settings

logger = logging.getLogger("stocknewsbr.api")

session = requests.Session()

retry_strategy = Retry(

    total=3,
    backoff_factor=0.3,

    status_forcelist=[429, 500, 502, 503, 504]

)

adapter = HTTPAdapter(

    max_retries=retry_strategy,
    pool_connections=10,
    pool_maxsize=10

)

session.mount("http://", adapter)
session.mount("https://", adapter)


def safe_get(url, params=None, headers=None):

    try:

        response = session.get(

            url,
            params=params,
            headers=headers,
            timeout=settings.API_TIMEOUT

        )

        response.raise_for_status()

        return response

    except requests.exceptions.Timeout:

        logger.warning("API timeout")

    except requests.exceptions.RequestException as e:

        logger.error(f"API error: {e}")

    return None