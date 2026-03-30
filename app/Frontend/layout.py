# =====================================================
# STOCKNEWSBR WEB WORKSPACE LAYOUT
# =====================================================

from typing import Dict, List


TABS: List[Dict[str, str]] = [
    {"id": "home", "title": "Inicio", "icon": "home"},
    {"id": "heatmap", "title": "IA Heat Map", "icon": "heatmap"},
    {"id": "radar", "title": "IA Radar", "icon": "radar"},
    {"id": "breakout-probability", "title": "IA Breakout Probability", "icon": "breakout"},
    {"id": "volatility-squeeze", "title": "IA Volatility Squeeze", "icon": "volatility"},
    {"id": "institutional-flow", "title": "IA Institutional Flow", "icon": "flow"},
    {"id": "smart-money", "title": "IA Smart Money", "icon": "smart-money"},
    {"id": "accumulation", "title": "IA Accumulation", "icon": "accumulation"},
    {"id": "liquidity-sweep", "title": "IA Liquidity Sweep", "icon": "liquidity-sweep"},
    {"id": "liquidity-map", "title": "IA Liquidity Map", "icon": "liquidity-map"},
    {"id": "market-regime", "title": "IA Market Regime", "icon": "market-regime"},
    {"id": "master-score", "title": "IA Master Score", "icon": "score"},
    {"id": "grafico", "title": "IA Grafico", "icon": "chart"},
    {"id": "ticker-rooms", "title": "Ticker Rooms", "icon": "chat"},
    {"id": "education", "title": "Ajuda Educacional", "icon": "help"},
]


def get_layout() -> Dict[str, List[Dict[str, str]]]:
    return {"tabs": [tab.copy() for tab in TABS]}
