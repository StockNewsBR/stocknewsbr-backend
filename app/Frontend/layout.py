# =====================================================
# STOCKNEWSBR WEB WORKSPACE LAYOUT
# =====================================================

from typing import Dict, List


TABS: List[Dict[str, str]] = [
    {"id": "home", "title": "Inicio", "icon": "home"},
    {"id": "flow", "title": "Flow IA", "icon": "flow"},
    {"id": "liquidity", "title": "Liquidity IA", "icon": "liquidity"},
    {"id": "trend", "title": "Trend IA", "icon": "trend"},
    {"id": "momentum", "title": "Momentum IA", "icon": "momentum"},
    {"id": "smart-money", "title": "IA Smart Money", "icon": "smart-money"},
    {"id": "risk", "title": "Risk IA", "icon": "risk"},
    {"id": "news-ia", "title": "News IA", "icon": "news"},
    {"id": "macro", "title": "Macro IA", "icon": "macro"},
    {"id": "regime", "title": "Regime IA", "icon": "regime"},
    {"id": "grafico", "title": "IA Grafico", "icon": "chart"},
    {"id": "observability", "title": "Observabilidade", "icon": "status"},
    {"id": "ticker-rooms", "title": "Ticker Rooms", "icon": "chat"},
    {"id": "education", "title": "Ajuda Educacional", "icon": "help"},
]


def get_layout() -> Dict[str, List[Dict[str, str]]]:
    return {"tabs": [tab.copy() for tab in TABS]}
