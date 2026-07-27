import json
import os

from app.Frontend.layout import get_layout

_DIR = os.path.dirname(os.path.abspath(__file__))
_HTML_PATH = os.path.join(_DIR, "trader_terminal.html")
with open(_HTML_PATH, "r", encoding="utf-8") as _f:
    _TEMPLATE = _f.read()


def get_terminal(focused_tab: str | None = None, token: str | None = None) -> str:
    tabs = get_layout()["tabs"]
    initial_tab = focused_tab or "home"

    embedded_tabs = json.dumps(tabs)
    focused_tab_json = json.dumps(initial_tab)
    embedded_token = json.dumps(token or "")

    html = _TEMPLATE.replace("__FALLBACK_TABS__", embedded_tabs)
    html = html.replace("__FOCUSED_TAB__", focused_tab_json)
    html = html.replace("__AUTH_TOKEN__", embedded_token)

    return html
