# =====================================================
# SYSTEM MONITOR
# Fast + Crash Safe
# =====================================================

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from sqlalchemy import text

from app.database import engine
from app.system.maintenance_mode import is_maintenance
from app.cache.signal_cache import signal_cache


logger = logging.getLogger("stocknewsbr.monitor")


# =====================================================
# DATABASE CHECK
# =====================================================

def check_database() -> str:

    try:

        with engine.connect() as conn:

            conn.execute(text("SELECT 1"))

        return "online"

    except Exception as e:

        logger.error(f"Database error: {e}")

        return "offline"


# =====================================================
# ENGINE CHECK
# =====================================================

def check_engine() -> str:

    try:

        signals = signal_cache.get()

        if signals is None:
            return "idle"

        if isinstance(signals, list) and len(signals) > 0:
            return "running"

        return "idle"

    except Exception as e:

        logger.error(f"Engine error: {e}")

        return "error"


# =====================================================
# SERVICE CHECK
# =====================================================

def check_service(name: str) -> str:

    try:

        if is_maintenance(name):
            return "maintenance"

        return "active"

    except Exception as e:

        logger.error(f"{name} status error: {e}")

        return "unknown"


# =====================================================
# SIGNAL CACHE CHECK
# =====================================================

def check_signal_cache() -> Dict[str, Any]:

    try:

        signals = signal_cache.get()

        if not isinstance(signals, list) or len(signals) == 0:

            return {
                "status": "empty",
                "signals": 0
            }

        return {
            "status": "active",
            "signals": len(signals)
        }

    except Exception as e:

        logger.error(f"Signal cache error: {e}")

        return {
            "status": "error",
            "signals": 0
        }


# =====================================================
# SYSTEM STATUS
# =====================================================

def get_system_status() -> Dict[str, Any]:

    try:

        return {

            "timestamp": datetime.now(timezone.utc).isoformat(),

            "api": "running",

            "engine": check_engine(),

            "database": check_database(),

            "signal_cache": check_signal_cache(),

            "telegram": check_service("telegram"),

            "web": check_service("web"),

            "app": check_service("app")

        }

    except Exception as e:

        logger.error(f"System monitor error: {e}")

        return {

            "status": "error",

            "message": str(e)

        }