# =====================================================
# STOCKNEWSBR WEB WIDGETS
# Fast + Safe
# =====================================================

from typing import Any, Dict, List


# =====================================================
# RADAR
# =====================================================

def radar_widget(data: Any) -> Dict[str, Any]:

    if data is None:
        data = []

    return {

        "type": "radar",

        "data": data

    }


# =====================================================
# HEATMAP
# =====================================================

def heatmap_widget(data: Any) -> Dict[str, Any]:

    if data is None:
        data = {}

    return {

        "type": "heatmap",

        "data": data

    }


# =====================================================
# NARRATIVE
# =====================================================

def narrative_widget(text: Any) -> Dict[str, Any]:

    if not isinstance(text, str):
        text = ""

    return {

        "type": "narrative",

        "text": text

    }


# =====================================================
# SIGNAL TABLE
# =====================================================

def signal_table(signals: Any) -> Dict[str, Any]:

    if not isinstance(signals, list):
        signals = []

    return {

        "type": "table",

        "rows": list(signals)

    }