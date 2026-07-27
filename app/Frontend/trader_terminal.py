import json
import os
from app.Frontend.layout import get_layout

_HTML_TEMPLATE = None

def get_terminal(focused_tab: str | None = None, token: str | None = None):
    global _HTML_TEMPLATE

    tabs = get_layout()["tabs"]
    initial_tab = focused_tab or "home"
    embedded_tabs = json.dumps(tabs)
    embedded_token = json.dumps(token or "")

    if _HTML_TEMPLATE is None:
        html_path = os.path.join(os.path.dirname(__file__), "trader_terminal.html")
        with open(html_path, "r", encoding="utf-8") as f:
            _HTML_TEMPLATE = f.read()

    return _HTML_TEMPLATE.replace(
        "__FALLBACK_TABS__", embedded_tabs
    ).replace(
        "__FOCUSED_TAB__", json.dumps(initial_tab)
    ).replace(
        "__AUTH_TOKEN__", embedded_token
    )
