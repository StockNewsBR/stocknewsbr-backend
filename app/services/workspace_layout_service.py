import json
import threading
import time
from pathlib import Path

from app.Frontend.layout import get_layout


LAYOUT_STORE_PATH = Path("data/workspace_layouts.json")
_lock = threading.RLock()
DEFAULT_CHART_SETTINGS = {
    "show_markers": True,
    "show_zones": True,
    "show_price_line": True,
    "show_vwap": True,
    "show_averages": True,
    "show_macd": False,
    "show_rsi": False,
    "show_supertrend": True,
    "show_volume": True,
}


def _normalize_chart_settings(chart_settings):
    source = chart_settings if isinstance(chart_settings, dict) else {}
    return {
        key: bool(source.get(key, default_value))
        for key, default_value in DEFAULT_CHART_SETTINGS.items()
    }


def _default_layout():
    return {
        "tabs": [tab["id"] for tab in get_layout()["tabs"]],
        "pinned_ticker": "PETR4",
        "opened_popouts": [],
        "chart_settings": dict(DEFAULT_CHART_SETTINGS),
        "updated_at": int(time.time()),
    }


def _load_store():
    with _lock:
        if not LAYOUT_STORE_PATH.exists():
            return {}

        try:
            return json.loads(LAYOUT_STORE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}


def _save_store(store):
    with _lock:
        LAYOUT_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAYOUT_STORE_PATH.write_text(
            json.dumps(store, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )


def get_user_workspace_layout(user_id: int):
    store = _load_store()
    key = str(user_id)
    layout = store.get(key) or _default_layout()
    layout.setdefault("tabs", _default_layout()["tabs"])
    layout.setdefault("pinned_ticker", "PETR4")
    layout.setdefault("opened_popouts", [])
    layout["chart_settings"] = _normalize_chart_settings(layout.get("chart_settings"))
    layout.setdefault("updated_at", int(time.time()))
    return layout


def save_user_workspace_layout(user_id: int, layout: dict):
    safe_layout = _default_layout()
    payload = dict(layout or {})
    valid_tabs = {tab["id"] for tab in get_layout()["tabs"]}

    tabs = payload.get("tabs")
    if isinstance(tabs, list) and tabs:
        deduped_tabs = []
        seen = set()

        for tab in tabs:
            tab_id = str(tab)
            if tab_id in valid_tabs and tab_id not in seen:
                deduped_tabs.append(tab_id)
                seen.add(tab_id)

        if deduped_tabs:
            safe_layout["tabs"] = deduped_tabs

    pinned_ticker = payload.get("pinned_ticker")
    if pinned_ticker:
        safe_layout["pinned_ticker"] = str(pinned_ticker).upper()

    opened_popouts = payload.get("opened_popouts")
    if isinstance(opened_popouts, list):
        safe_layout["opened_popouts"] = [
            str(tab)
            for tab in opened_popouts
            if str(tab) in valid_tabs
        ]

    chart_settings = payload.get("chart_settings")
    if isinstance(chart_settings, dict):
        safe_layout["chart_settings"] = _normalize_chart_settings(chart_settings)

    safe_layout["updated_at"] = int(time.time())

    store = _load_store()
    store[str(user_id)] = safe_layout
    _save_store(store)
    return safe_layout
