from app.Frontend.layout import get_layout
from app.cache.snapshot_cache import get_snapshot_info, get_snapshot_signals
from app.services.help_center_service import get_help_center_blueprint
from app.services.legal_service import get_public_bootstrap
from app.services.media_service import get_media_status
from app.services.push_service import get_push_status
from app.services.ranking import get_ranking
from app.services.workspace_layout_service import get_user_workspace_layout
from app.social.posts import get_posts
from app.services.ticker_room_service import list_room_messages
from app.system.system_metrics import get_metrics_snapshot


def _tab_routes():
    return {
        "home": "/web/workspace/data",
        "heatmap": "/web/workspace/data",
        "radar": "/web/workspace/data",
        "breakout-probability": "/web/workspace/data",
        "volatility-squeeze": "/web/workspace/data",
        "institutional-flow": "/web/workspace/data",
        "smart-money": "/web/workspace/data",
        "accumulation": "/web/workspace/data",
        "liquidity-sweep": "/web/workspace/data",
        "liquidity-map": "/web/workspace/data",
        "market-regime": "/web/workspace/data",
        "master-score": "/web/workspace/data",
        "grafico": "/web/chart/PETR4",
        "ticker-rooms": "/web/workspace/data",
        "education": "/web/help-center",
    }


def get_workspace_data(user_id: int | None = None, channel: str = "web"):
    bootstrap = get_public_bootstrap()
    metrics = get_metrics_snapshot()
    snapshot_info = get_snapshot_info()
    top_signals = get_snapshot_signals(limit=12)
    ranking = get_ranking()[:12]
    featured_posts = get_posts(limit=10)
    help_center = get_help_center_blueprint()
    media_status = get_media_status()
    push_status = get_push_status()
    layout = get_user_workspace_layout(user_id or 0)
    saved_order = layout.get("tabs", [])
    pinned_ticker = layout.get("pinned_ticker", "PETR4")

    base_tabs = {tab["id"]: dict(tab) for tab in get_layout()["tabs"]}
    ordered_ids = [tab_id for tab_id in saved_order if tab_id in base_tabs]

    for tab_id in base_tabs:
        if tab_id not in ordered_ids:
            ordered_ids.append(tab_id)

    tabs = []

    for tab_id in ordered_ids:
        item = dict(base_tabs[tab_id])
        item["route"] = _tab_routes().get(item["id"], "/web/workspace/data")
        item["popout_route"] = f"/web/terminal/popout/{item['id']}" if channel == "web" else None
        item["detachable"] = channel == "web"
        item["monitor_ready"] = channel == "web"
        tabs.append(item)

    return {
        "brand": bootstrap["brand"],
        "workspace_mode": "multi_monitor" if channel == "web" else "single_screen",
        "channel": channel,
        "tabs": tabs,
        "top_signals": top_signals,
        "ranking": ranking,
        "featured_posts": featured_posts,
        "ticker_room_preview": {
            "symbol": pinned_ticker,
            "messages": list_room_messages(pinned_ticker, limit=12),
        },
        "help_center": help_center,
        "media": media_status,
        "push": push_status,
        "pricing": bootstrap["pricing"],
        "launch_roadmap": bootstrap["launch_roadmap"],
        "ai_modules": bootstrap["ai_modules"],
        "social_features": bootstrap["social_features"],
        "layout": layout,
        "status": {
            "engine_cycles": metrics["engine_cycles"],
            "signals_generated": metrics["signals_generated"],
            "assets_scanned": metrics["assets_scanned"],
            "cache_age": metrics["cache_age"],
            "snapshot_signals": snapshot_info.get("signals", 0),
            "http_requests": metrics["http_requests"],
            "ws_connections": metrics["ws_connections"],
            "chat_messages": metrics["chat_messages"],
        },
        "chart_capabilities": {
            "overlay_markers": True,
            "moving_averages": True,
            "signal_zones": True,
            "trade_annotations": True,
        },
        "platform_notes": {
            "tabs_detachable": channel == "web",
            "multi_monitor_supported": channel == "web",
            "mobile_behavior": (
                "No app as tabs ficam internas em tela unica."
                if channel != "web"
                else "Na web as tabs podem ser destacadas para outros monitores."
            ),
        },
    }
