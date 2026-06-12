from __future__ import annotations

from typing import Any, Dict, List

from app.Frontend.layout import get_layout
from app.cache.snapshot_cache import get_snapshot
from app.ai.final_decision import ensure_final_decision_rows, final_decision_items
from app.ai.historical_confidence import ensure_historical_confidence_rows, historical_confidence_items
from app.ai.institutional_conviction import conviction_items, ensure_institutional_conviction_rows
from app.ai.institutional_priority import ensure_institutional_priority_rows, priority_items
from app.ai.institutional_radar import ensure_institutional_radar_rows, institutional_radar_items
from app.ai.institutional_ranking import ensure_institutional_ranking_rows, institutional_ranking_items
from app.ai.operational_rules import ensure_operational_rules_rows
from app.services.ai_alert_history_service import persist_ai_alert_history
from app.ai.ai_specialists import OFFICIAL_AI_TOOL_KEYS
from app.services.help_center_service import get_help_center_blueprint
from app.services.legal_service import get_public_bootstrap
from app.services.media_service import get_media_status
from app.services.push_service import get_push_status
from app.services.ranking import get_ranking
from app.services.snapshot_contract import is_actionable_snapshot_row, is_blocked_snapshot_row
from app.services.ticker_room_service import list_room_messages
from app.services.workspace_layout_service import get_user_workspace_layout
from app.social.posts import get_posts
from app.api import routes_system
from app.system.system_metrics import get_metrics_snapshot
from app.telegram.telegram_alert_engine import get_telegram_alert_history, get_telegram_health


def _tab_routes() -> Dict[str, str]:
    return {
        "home": "/web/workspace/data",
        "flow": "/web/workspace/data",
        "liquidity": "/web/workspace/data",
        "trend": "/web/workspace/data",
        "momentum": "/web/workspace/data",
        "smart-money": "/web/workspace/data",
        "risk": "/web/workspace/data",
        "news-ia": "/web/workspace/data",
        "macro": "/web/workspace/data",
        "regime": "/web/workspace/data",
        "grafico": "/web/chart/PETR4",
        "ticker-rooms": "/web/workspace/data",
        "education": "/web/help-center",
    }


def _safe_rows(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _empty_ai_outputs() -> Dict[str, List[Dict[str, Any]]]:
    return {key: [] for key in OFFICIAL_AI_TOOL_KEYS}

def _coerce_ai_outputs(value: Any) -> Dict[str, List[Dict[str, Any]]]:
    outputs = _empty_ai_outputs()

    if not isinstance(value, dict):
        return outputs

    for key in outputs:
        outputs[key] = _safe_rows(value.get(key))

    return outputs


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 0:
        return number
    return None


_BLOCKED_AI_DATA_STATES = {
    "score_only",
    "score only",
    "missing",
    "empty",
    "stale",
    "no_price",
    "no-price",
    "no price",
    "provider_failed",
    "provider-failed",
    "provider failed",
    "failed",
    "error",
    "timeout",
    "unavailable",
    "invalid",
}


def _plain(value: Any) -> str:
    text = str(value or "").strip().upper()
    for source, target in (
        ("Ã", "A"),
        ("Á", "A"),
        ("À", "A"),
        ("Â", "A"),
        ("É", "E"),
        ("Ê", "E"),
        ("Í", "I"),
        ("Ó", "O"),
        ("Ô", "O"),
        ("Õ", "O"),
        ("Ú", "U"),
        ("Ç", "C"),
    ):
        text = text.replace(source, target)
    return " ".join(text.split())


def _extend_reasons(reasons: List[str], values: Any, fallback: str) -> None:
    if isinstance(values, str) and values.strip():
        reasons.append(values.strip())
        return
    if isinstance(values, (list, tuple, set)):
        added = False
        for value in values:
            text = str(value or "").strip()
            if text:
                reasons.append(text)
                added = True
        if added:
            return
    reasons.append(fallback)


def _workspace_block_reasons(row: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    audit_status = _plain(row.get("audit_status") or row.get("auditor_status"))
    operational_status = _plain(row.get("operational_status"))
    final_decision = _plain(row.get("final_decision"))

    if row.get("blocked_by_auditor") is True or audit_status == "BLOCKED":
        _extend_reasons(reasons, row.get("audit_blocks"), "Auditor BLOCKED")
    if operational_status == "BLOCKED":
        _extend_reasons(reasons, row.get("operational_blocks"), "Operational BLOCKED")
    if "NAO OPERAR AGORA" in final_decision or final_decision == "NO TRADE":
        _extend_reasons(reasons, row.get("final_decision_blocks"), "Final Decision NAO OPERAR AGORA")
    if row.get("radar_no_trade_now") is True:
        _extend_reasons(reasons, row.get("radar_blocked_reasons"), "Radar NO_TRADE")
    if row.get("decision_ready") is not True:
        reasons.append("Decision Ready False")
    if is_blocked_snapshot_row(row) and not reasons:
        _extend_reasons(reasons, row.get("blocked_reasons") or row.get("warnings"), "Snapshot contract blocked")

    return list(dict.fromkeys(reasons))


def _blocked_ai_state(value: Any) -> bool:
    if value is None:
        return False
    normalized = str(value).strip().lower()
    if not normalized:
        return False
    return any(state in normalized for state in _BLOCKED_AI_DATA_STATES)


def _is_operational_ai_row(row: Dict[str, Any]) -> bool:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    state_values = [
        row.get("data_quality"),
        row.get("dataQuality"),
        row.get("quote_status"),
        row.get("status"),
        row.get("provider_status"),
        row.get("market_data_status"),
        metrics.get("data_quality"),
        metrics.get("dataQuality"),
        metrics.get("quote_status"),
        metrics.get("status"),
        metrics.get("provider_status"),
        metrics.get("market_data_status"),
    ]
    if any(_blocked_ai_state(value) for value in state_values):
        return False
    if row.get("stale") is True or row.get("is_stale") is True:
        return False
    if row.get("provider_failed") is True or row.get("provider_error"):
        return False
    return (
        _positive_number(row.get("price") or metrics.get("price")) is not None
        and _positive_number(row.get("volume") or metrics.get("volume")) is not None
    )


def _has_operational_ai_outputs(outputs: Dict[str, List[Dict[str, Any]]]) -> bool:
    return any(_is_operational_ai_row(row) for rows in outputs.values() for row in rows)


def get_workspace_data(user_id: int | None = None, channel: str = "web") -> Dict[str, Any]:
    bootstrap = get_public_bootstrap()
    metrics = get_metrics_snapshot()
    snapshot = get_snapshot()
    if not isinstance(snapshot, dict):
        snapshot = {}
    snapshot_signals = ensure_institutional_radar_rows(
        _safe_rows(snapshot.get("signals")),
        ai_tools=snapshot.get("ai_tools") if isinstance(snapshot.get("ai_tools"), dict) else None,
        market_pulse=snapshot.get("market_pulse") if isinstance(snapshot.get("market_pulse"), dict) else None,
    )
    snapshot_signals = ensure_institutional_ranking_rows(
        snapshot_signals,
        ai_tools=snapshot.get("ai_tools") if isinstance(snapshot.get("ai_tools"), dict) else None,
        market_pulse=snapshot.get("market_pulse") if isinstance(snapshot.get("market_pulse"), dict) else None,
    )
    snapshot_signals = ensure_historical_confidence_rows(snapshot_signals)
    snapshot_signals = ensure_operational_rules_rows(
        snapshot_signals,
        ai_tools=snapshot.get("ai_tools") if isinstance(snapshot.get("ai_tools"), dict) else None,
        market_pulse=snapshot.get("market_pulse") if isinstance(snapshot.get("market_pulse"), dict) else None,
    )
    snapshot_signals = ensure_institutional_conviction_rows(
        snapshot_signals,
        ai_tools=snapshot.get("ai_tools") if isinstance(snapshot.get("ai_tools"), dict) else None,
        market_pulse=snapshot.get("market_pulse") if isinstance(snapshot.get("market_pulse"), dict) else None,
    )
    snapshot_signals = ensure_institutional_priority_rows(
        snapshot_signals,
        ai_tools=snapshot.get("ai_tools") if isinstance(snapshot.get("ai_tools"), dict) else None,
        market_pulse=snapshot.get("market_pulse") if isinstance(snapshot.get("market_pulse"), dict) else None,
    )
    snapshot_signals = ensure_final_decision_rows(
        snapshot_signals,
        ai_tools=snapshot.get("ai_tools") if isinstance(snapshot.get("ai_tools"), dict) else None,
        market_pulse=snapshot.get("market_pulse") if isinstance(snapshot.get("market_pulse"), dict) else None,
    )
    actionable_signals = [row for row in snapshot_signals if is_actionable_snapshot_row(row)]
    radar_signals = institutional_radar_items(actionable_signals, limit=50)
    ranking_signals = institutional_ranking_items(snapshot_signals, limit=200)
    historical_confidence_rows = historical_confidence_items(snapshot_signals, limit=200)
    conviction_rows = conviction_items(snapshot_signals, limit=200)
    priority_rows = priority_items(snapshot_signals, limit=200)
    final_decision_rows = final_decision_items(snapshot_signals, limit=200)
    blocked_signals = []
    for row in snapshot_signals:
        block_reasons = _workspace_block_reasons(row)
        if not block_reasons:
            continue
        blocked_row = dict(row)
        blocked_row["workspace_block_reasons"] = block_reasons
        blocked_row["blocked_reason"] = "; ".join(block_reasons[:5])
        blocked_signals.append(blocked_row)
    top_signals = radar_signals[:12] if radar_signals else actionable_signals[:12]
    symbol_snapshots = snapshot.get("symbol_snapshots") if isinstance(snapshot.get("symbol_snapshots"), dict) else {}
    market_snapshot = {
        "schema_version": snapshot.get("schema_version"),
        "generated_at": snapshot.get("generated_at"),
        "source": snapshot.get("source"),
        "stale": bool(snapshot.get("stale")),
        "market_snapshot_interval_seconds": snapshot.get("market_snapshot_interval_seconds"),
        "ai_snapshot_interval_seconds": snapshot.get("ai_snapshot_interval_seconds"),
        "stats": snapshot.get("stats") if isinstance(snapshot.get("stats"), dict) else {},
        "data_status": snapshot.get("data_status") if isinstance(snapshot.get("data_status"), dict) else {},
        "market_pulse": snapshot.get("market_pulse") if isinstance(snapshot.get("market_pulse"), dict) else {},
        "auditor": snapshot.get("auditor") if isinstance(snapshot.get("auditor"), dict) else {},
        "institutional_auditor": snapshot.get("institutional_auditor") if isinstance(snapshot.get("institutional_auditor"), dict) else {},
        "master_score": snapshot.get("master_score") if isinstance(snapshot.get("master_score"), dict) else {},
        "master_scores": snapshot.get("master_scores") if isinstance(snapshot.get("master_scores"), list) else [],
        "strategic_panel": snapshot.get("strategic_panel") if isinstance(snapshot.get("strategic_panel"), dict) else {},
        "strategic_panels": snapshot.get("strategic_panels") if isinstance(snapshot.get("strategic_panels"), list) else [],
        "strategic_panel_summary": snapshot.get("strategic_panel_summary") or "",
        "institutional_radar": snapshot.get("institutional_radar") if isinstance(snapshot.get("institutional_radar"), list) else radar_signals[:20],
        "radar_metrics": snapshot.get("radar_metrics") if isinstance(snapshot.get("radar_metrics"), dict) else {},
        "institutional_ranking": snapshot.get("institutional_ranking") if isinstance(snapshot.get("institutional_ranking"), list) else ranking_signals[:20],
        "ranking_metrics": snapshot.get("ranking_metrics") if isinstance(snapshot.get("ranking_metrics"), dict) else {},
        "historical_confidence": snapshot.get("historical_confidence") if isinstance(snapshot.get("historical_confidence"), dict) else (historical_confidence_rows[0] if historical_confidence_rows else {}),
        "historical_confidences": snapshot.get("historical_confidences") if isinstance(snapshot.get("historical_confidences"), list) else historical_confidence_rows[:20],
        "historical_confidence_metrics": snapshot.get("historical_confidence_metrics") if isinstance(snapshot.get("historical_confidence_metrics"), dict) else {},
        "operational_rules": snapshot.get("operational_rules") if isinstance(snapshot.get("operational_rules"), list) else snapshot_signals[:20],
        "operational_rules_metrics": snapshot.get("operational_rules_metrics") if isinstance(snapshot.get("operational_rules_metrics"), dict) else {},
        "institutional_convictions": snapshot.get("institutional_convictions") if isinstance(snapshot.get("institutional_convictions"), list) else conviction_rows[:20],
        "institutional_conviction": snapshot.get("institutional_conviction") if isinstance(snapshot.get("institutional_conviction"), dict) else (conviction_rows[0] if conviction_rows else {}),
        "conviction_metrics": snapshot.get("conviction_metrics") if isinstance(snapshot.get("conviction_metrics"), dict) else {},
        "institutional_priorities": snapshot.get("institutional_priorities") if isinstance(snapshot.get("institutional_priorities"), list) else priority_rows[:20],
        "institutional_priority": snapshot.get("institutional_priority") if isinstance(snapshot.get("institutional_priority"), dict) else (priority_rows[0] if priority_rows else {}),
        "priority_metrics": snapshot.get("priority_metrics") if isinstance(snapshot.get("priority_metrics"), dict) else {},
        "final_decisions": snapshot.get("final_decisions") if isinstance(snapshot.get("final_decisions"), list) else final_decision_rows[:20],
        "final_decision": snapshot.get("final_decision") if isinstance(snapshot.get("final_decision"), dict) else (final_decision_rows[0] if final_decision_rows else {}),
        "final_decision_metrics": snapshot.get("final_decision_metrics") if isinstance(snapshot.get("final_decision_metrics"), dict) else {},
        "institutional_consistency": snapshot.get("institutional_consistency") if isinstance(snapshot.get("institutional_consistency"), dict) else {},
        "institutional_consistency_metrics": snapshot.get("institutional_consistency_metrics") if isinstance(snapshot.get("institutional_consistency_metrics"), dict) else {},
        "symbol_count": len(symbol_snapshots),
    }
    data_status = market_snapshot["data_status"] if isinstance(market_snapshot.get("data_status"), dict) else {}
    ranking_source = get_ranking() or []
    ranking_rows = _safe_rows(ranking_source if isinstance(ranking_source, list) else [])
    ranking = ranking_signals[:200] if ranking_signals else actionable_signals[:200] if actionable_signals else ranking_rows[:200]
    featured_posts = _safe_rows(get_posts(limit=10))
    ai_outputs = _coerce_ai_outputs(snapshot.get("ai_tools"))
    market_decision = snapshot.get("decision") if isinstance(snapshot, dict) else {}

    if not isinstance(market_decision, dict) or not market_decision:
        market_decision = {
            "trade_action": "NO_DECISION",
            "trade_direction": "flat",
            "decision_ready": False,
            "decision_state": "WAIT",
            "operational_message": "⚠️ NÃO OPERAR AGORA",
            "no_trade_reasons": ["snapshot inválido"],
            "can_trade": False,
            "data_quality": "score_only",
            "reason": "Snapshot ainda sem decisao consolidada pronta.",
        }

    ai_outputs = persist_ai_alert_history(ai_outputs)

    help_center = get_help_center_blueprint()
    media_status = get_media_status()
    push_status = get_push_status()
    observability = routes_system.observability_dashboard()
    telegram_alert_history = get_telegram_alert_history(limit=30)
    telegram_alerts = {
        "health": get_telegram_health(),
        "latest": telegram_alert_history[:20],
        "sent": [item for item in telegram_alert_history if item.get("status") == "sent"][:10],
        "blocked": [item for item in telegram_alert_history if item.get("status") == "blocked"][:10],
        "discarded": [item for item in telegram_alert_history if item.get("status") in {"discarded", "deduplicated", "cooldown"}][:10],
    }
    layout = get_user_workspace_layout(user_id or 0)
    saved_order = layout.get("tabs", [])
    pinned_ticker = layout.get("pinned_ticker", "PETR4")

    base_tabs = {tab["id"]: dict(tab) for tab in get_layout()["tabs"]}
    ordered_ids = [tab_id for tab_id in saved_order if tab_id in base_tabs]

    for tab_id in base_tabs:
        if tab_id not in ordered_ids:
            ordered_ids.append(tab_id)

    tabs: List[Dict[str, Any]] = []
    tab_routes = _tab_routes()

    for tab_id in ordered_ids:
        item = dict(base_tabs[tab_id])
        item["route"] = tab_routes.get(item["id"], "/web/workspace/data")
        item["popout_route"] = (
            f"/web/terminal/popout/{item['id']}" if channel == "web" else None
        )
        item["detachable"] = channel == "web"
        item["monitor_ready"] = channel == "web"
        tabs.append(item)

    return {
        "brand": bootstrap["brand"],
        "workspace_mode": "multi_monitor" if channel == "web" else "single_screen",
        "channel": channel,
        "tabs": tabs,
        "top_signals": top_signals,
        "institutional_radar": radar_signals[:20],
        "institutional_ranking": ranking_signals[:20],
        "historical_confidence": market_snapshot["historical_confidence"],
        "historical_confidences": historical_confidence_rows[:20],
        "operational_rules": market_snapshot["operational_rules"],
        "institutional_convictions": conviction_rows[:20],
        "institutional_conviction": market_snapshot["institutional_conviction"],
        "institutional_priorities": priority_rows[:20],
        "institutional_priority": market_snapshot["institutional_priority"],
        "final_decisions": final_decision_rows[:20],
        "final_decision": market_snapshot["final_decision"],
        "institutional_consistency": market_snapshot["institutional_consistency"],
        "ranking": ranking,
        "blocked_signals": blocked_signals[:50],
        "symbol_snapshots": symbol_snapshots,
        "market_snapshot": market_snapshot,
        "featured_posts": featured_posts,
        "ticker_room_preview": {
            "symbol": pinned_ticker,
            "messages": list_room_messages(pinned_ticker, limit=12),
        },
        "help_center": help_center,
        "media": media_status,
        "push": push_status,
        "observability": observability,
        "telegram_alerts": telegram_alerts,
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
            "snapshot_signals": len(snapshot_signals),
            "http_requests": metrics["http_requests"],
            "ws_connections": metrics["ws_connections"],
            "chat_messages": metrics["chat_messages"],
            "snapshot_generated_at": market_snapshot.get("generated_at"),
            "snapshot_source": market_snapshot.get("source"),
            "snapshot_stale": market_snapshot.get("stale"),
            "snapshot_actionable": data_status.get("actionable", 0),
            "snapshot_priced": data_status.get("priced", 0),
            "snapshot_score_only": data_status.get("score_only", 0),
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
        "ai_tools": ai_outputs,
        "market_decision": market_decision if isinstance(market_decision, dict) else {},
        "auditor": snapshot.get("auditor") if isinstance(snapshot.get("auditor"), dict) else {},
        "institutional_auditor": snapshot.get("institutional_auditor") if isinstance(snapshot.get("institutional_auditor"), dict) else {},
        "master_score": snapshot.get("master_score") if isinstance(snapshot.get("master_score"), dict) else {},
        "master_scores": snapshot.get("master_scores") if isinstance(snapshot.get("master_scores"), list) else [],
        "strategic_panel": snapshot.get("strategic_panel") if isinstance(snapshot.get("strategic_panel"), dict) else {},
        "strategic_panels": snapshot.get("strategic_panels") if isinstance(snapshot.get("strategic_panels"), list) else [],
        "strategic_panel_summary": snapshot.get("strategic_panel_summary") or "",
        "institutional_conviction": market_snapshot["institutional_conviction"],
        "institutional_priority": market_snapshot["institutional_priority"],
        "final_decision": market_snapshot["final_decision"],
        "institutional_consistency": market_snapshot["institutional_consistency"],
    }
