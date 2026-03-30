# =====================================================
# STOCKNEWSBR MAINTENANCE MODE
# =====================================================

import logging
import threading
from typing import Dict

logger = logging.getLogger("stocknewsbr.maintenance")

_maintenance_state: Dict[str, bool] = {
    "web": False,
    "app": False,
    "telegram": False,
}

_lock = threading.RLock()

DEFAULT_MESSAGE = "StockNewsBR em manutencao.\n\nVoltaremos em breve."


def is_maintenance(service: str) -> bool:
    if not service:
        return False

    try:
        with _lock:
            return bool(_maintenance_state.get(service, False))
    except Exception as exc:
        logger.error("Maintenance check error: %s", exc)
        return False


def enable_maintenance(service: str) -> bool:
    if not service:
        return False

    try:
        with _lock:
            if service not in _maintenance_state:
                logger.warning("Unknown maintenance service: %s", service)
                return False

            _maintenance_state[service] = True

        logger.warning("Maintenance enabled for %s", service)
        return True
    except Exception as exc:
        logger.error("Enable maintenance error: %s", exc)
        return False


def disable_maintenance(service: str) -> bool:
    if not service:
        return False

    try:
        with _lock:
            if service not in _maintenance_state:
                logger.warning("Unknown maintenance service: %s", service)
                return False

            _maintenance_state[service] = False

        logger.info("Maintenance disabled for %s", service)
        return True
    except Exception as exc:
        logger.error("Disable maintenance error: %s", exc)
        return False


def maintenance_status() -> Dict[str, bool]:
    try:
        with _lock:
            return dict(_maintenance_state)
    except Exception as exc:
        logger.error("Maintenance status error: %s", exc)
        return {}


def maintenance_message(service: str | None = None) -> str:
    del service
    return DEFAULT_MESSAGE
