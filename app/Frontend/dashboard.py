# =====================================================
# STOCKNEWSBR WEB DASHBOARD
# Fast + Crash Safe
# =====================================================

import logging
from typing import Dict, Any, List

from app.cache.signal_cache import signal_cache
from app.ai.market_heatmap import generate_heatmap
from app.ai.market_narrative import generate_market_narrative


logger = logging.getLogger("stocknewsbr.dashboard")


MAX_SIGNALS = 20


# =====================================================
# SAFE HEATMAP
# =====================================================

def safe_heatmap(signals: List[dict]) -> Dict[str, Any]:

    try:

        heatmap = generate_heatmap(signals)

        if not isinstance(heatmap, dict):
            return {}

        return heatmap

    except Exception as e:

        logger.warning(f"Heatmap generation failed: {e}")

        return {}


# =====================================================
# SAFE NARRATIVE
# =====================================================

def safe_narrative(heatmap: Dict[str, Any]) -> str:

    try:

        strength = heatmap.get("global", {}).get("market_strength", 0)

        narrative = generate_market_narrative(
            "Market",
            strength,
            5
        )

        if not isinstance(narrative, str):
            return "Market analysis unavailable."

        return narrative

    except Exception as e:

        logger.warning(f"Narrative generation failed: {e}")

        return "Market analysis unavailable."


# =====================================================
# DASHBOARD DATA
# =====================================================

def get_dashboard() -> Dict[str, Any]:

    try:

        signals = signal_cache.get()

        if not isinstance(signals, list):
            signals = []

        # copy to avoid mutation
        signals_copy = list(signals)

        # ------------------------------------------------
        # LIMIT SIGNALS
        # ------------------------------------------------

        top_signals = signals_copy[:MAX_SIGNALS]

        # ------------------------------------------------
        # HEATMAP
        # ------------------------------------------------

        heatmap = safe_heatmap(signals_copy)

        # ------------------------------------------------
        # MARKET SUMMARY
        # ------------------------------------------------

        narrative = safe_narrative(heatmap)

        return {

            "signals": top_signals,

            "heatmap": heatmap,

            "narrative": narrative,

            "total_signals": len(signals_copy)

        }

    except Exception as e:

        logger.error(f"Dashboard error: {e}")

        return {

            "signals": [],

            "heatmap": {},

            "narrative": "Market data unavailable.",

            "total_signals": 0

        }