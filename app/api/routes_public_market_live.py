import math
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import os as _os_premium_gate

from fastapi import APIRouter, Depends, Query

from app.dependencies import resolve_premium_entitlement

from app.cache.snapshot_cache import get_snapshot, get_snapshot_ticker
from app.engine.chart_signal_adapter import build_chart_signal_payload
from app.market.market_data_loader import (
    get_display_symbol,
    previous_session_close,
    session_change,
)
from app.services.chart_overlay_service import build_chart_overlays
from app.services.public_ai_tools_service import build_public_ai_tools_payload
from app.services.public_market_data_service import (
    build_crypto_intraday_rvol_contract,
    build_public_indices_payload,
    build_public_rsi_contract,
    cached_price_payloads,
    load_public_chart_rows,
    normalize_public_chart_zones,
    public_chart_as_of,
    public_daily_age_sessions,
    public_daily_freshness_status,
    schedule_quote_warmup,
)
from app.services.public_news_service import build_public_news_payload
from app.services.news_service import normalize_news_locale
from app.services.quote_service import (
    classify_quote_payload,
    empty_quote_payload,
    get_cached_quote_payload,
    is_usable_quote_payload,
    with_quote_diagnostics,
)
from app.services.score_display import attach_master_score_display_contract
from app.services.snapshot_contract import build_decision_envelope
from app.services.symbol_registry import (
    canonical_symbol,
    canonical_symbol_aliases,
    is_ambiguous_crypto_symbol,
    is_bdr_proxy_payload,
    is_bdr_symbol,
    provider_symbol,
    symbol_category,
)
from app.services.symbol_sanitizer import mark_symbol_cooldown, sanitize_market_symbol
from app.system.system_metrics import record_cache_access
from app.system.symbol_hydration import get_symbol_analysis, hydration_status, request_symbol_hydration, resolve_symbol_context


router = APIRouter(prefix="/public", tags=["Public Market Live"])
# BRFS3/JBSS3 left this blocklist: they now alias to live successors
# (MBRF3 / JBSS32) in the symbol registry, and the alias-based check would
# otherwise block the successors too.
_PUBLIC_MARKET_BLOCKED_SYMBOLS = {
    "ENBR3",
    "ENBR3.SA",
}

_CME_FUTURES_PROVIDER_SYMBOLS = {
    "NQ": "NQ=F",
    "MNQ": "MNQ=F",
    "MNO": "MNQ=F",
    "ES": "ES=F",
    "MES": "MES=F",
    "YM": "YM=F",
    "MYM": "MYM=F",
}

_B3_MINI_FUTURE_RE = re.compile(r"^(WIN|WDO)[FGHJKMNQUVXZ]\d{2}$")


def _is_b3_mini_future_symbol(symbol: str) -> bool:
    raw = _normalize_public_symbol(symbol)
    compact = raw[:-3] if raw.endswith(".SA") else raw
    return _B3_MINI_FUTURE_RE.match(compact) is not None


def _normalize_public_symbol(symbol: str, *, mark_cooldown: bool = True) -> str:
    if is_ambiguous_crypto_symbol(symbol):
        if mark_cooldown:
            mark_symbol_cooldown(symbol, "ambiguous_symbol")
        return ""
    sanitized = canonical_symbol(symbol) or sanitize_market_symbol(symbol, allow_provider_symbols=True)
    if mark_cooldown and not sanitized and symbol:
        mark_symbol_cooldown(symbol, "invalid_symbol")
    return sanitized or ""


def _safe_response_symbol(symbol: str) -> str:
    normalized = _normalize_public_symbol(symbol, mark_cooldown=False)
    if normalized:
        return _response_symbol(normalized)
    raw = str(symbol or "").upper().strip()
    safe = re.sub(r"[^A-Z0-9._=-]", "", raw)[:32]
    return safe or "INVALID_SYMBOL"


def _invalid_quote_payload(symbol: str, status: str, reason: str | None = None) -> dict:
    safe_symbol = _safe_response_symbol(symbol)
    payload = empty_quote_payload(safe_symbol, quote_status=status, reason=reason or status)
    payload["requested_symbol"] = safe_symbol
    return payload


def _empty_master_context() -> dict:
    return {
        "master_score": None,
        "master_score_raw": None,
        "master_score_source_scale": None,
        "decision_status": None,
        "decision_envelope": {},
        "master_direction": None,
        "master_conviction": None,
        "master_confidence": None,
        "master_summary": None,
        "master_reasoning": {},
        "master_risk": None,
        "master_status": None,
        "opinion_change_conditions": [],
        "strategic_panel": {},
        "strategic_panel_summary": "",
        "recommended_action": None,
        "radar_prioritization_score": None,
        "radar_priority_score": None,
        "radar_priority": None,
        "radar_level": None,
        "radar_reason": None,
        "radar_summary": None,
        "radar_no_trade_now": False,
        "radar_blocked_reasons": [],
        "ranking_opportunity_score": None,
        "ranking_classification": None,
        "ranking_reason": None,
        "ranking_summary": None,
        "ranking_eligible": None,
        "ranking_excluded_reasons": [],
        "historical_confidence_score": None,
        "historical_confidence_label": None,
        "historical_sample_size": None,
        "historical_win_rate": None,
        "historical_context_match": None,
        "historical_reason": None,
        "historical_warning": None,
        "operational_status": None,
        "operational_ready": None,
        "operational_score": None,
        "operational_blocks": [],
        "operational_warnings": [],
        "operational_summary": None,
        "conviction_score": None,
        "conviction_level": None,
        "conviction_summary": None,
        "conviction_factors": [],
        "conviction_conflicts": [],
        "priority_score": None,
        "priority_level": None,
        "priority_rank": None,
        "priority_summary": None,
        "priority_factors": [],
        "final_decision": None,
        "final_decision_score": None,
        "final_decision_summary": None,
        "final_decision_reason": None,
        "final_decision_blocks": [],
        "final_decision_confidence": None,
    }


def _invalid_insight_payload(symbol: str, status: str, provider_status: str, interval: str = "1D") -> dict:
    response_symbol = _safe_response_symbol(symbol)
    rsi_contract = build_public_rsi_contract(
        response_symbol,
        interval,
        [],
        empty_status="INSUFFICIENT_DATA",
        empty_reason=status,
    )
    return {
        "symbol": response_symbol,
        "score": None,
        **_empty_master_context(),
        **rsi_contract,
        "trend_bias": None,
        "signal": None,
        "summary": {
            "source": status,
            "fallback": True,
            "status": status,
            "provider_status": provider_status,
        },
        "fallback": True,
        "status": status,
        "provider_status": provider_status,
    }


def _invalid_bundle_payload(symbol: str, interval: str, limit: int, status: str, provider_status: str, locale: str = "pt-BR") -> dict:
    del limit
    response_symbol = _safe_response_symbol(symbol)
    quote = _invalid_quote_payload(symbol, status, provider_status)
    normalized_locale = normalize_news_locale(locale)
    return _json_safe_payload({
        "symbol": response_symbol,
        "quote": quote,
        "insight": _invalid_insight_payload(symbol, status, provider_status, interval=interval),
        "chart": _empty_chart_payload(response_symbol, interval, provider_status, status=status),
        "news": {"symbol": response_symbol, "items": [], "count": 0, "source": status, "status": status, "locale": normalized_locale},
        "ai_tools": {"tools": {}, "source": status, "using_fallback": False, "go_live_ready": False},
        "source": "cache_snapshot_bundle",
    })


def _dedupe_public_symbols(symbols) -> list[str]:
    seen = set()
    result = []
    for symbol in symbols:
        value = _normalize_public_symbol(symbol)
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _dedupe_alias_symbols(symbols) -> list[str]:
    seen = set()
    result = []
    for symbol in symbols:
        value = str(symbol or "").upper().strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _response_symbol(symbol: str) -> str:
    value = get_display_symbol(_normalize_public_symbol(symbol))
    if value.endswith(".SA"):
        value = value[:-3]
    if value.endswith("-USD"):
        value = value.replace("-USD", "USD")
    if value.endswith("USDT"):
        value = f"{value[:-4]}USD"
    return value


def _symbol_aliases(symbol: str) -> list[str]:
    raw = _normalize_public_symbol(symbol)
    if not raw:
        return []

    display = get_display_symbol(raw)
    aliases = [*canonical_symbol_aliases(raw), raw, display]
    for candidate in list(aliases):
        base = candidate[:-3] if candidate.endswith(".SA") else candidate
        compact = base.replace("-USD", "USD")
        if compact.endswith("USDT"):
            compact = f"{compact[:-4]}USD"

        aliases.extend([base, compact])
        if compact in _CME_FUTURES_PROVIDER_SYMBOLS:
            aliases.append(_CME_FUTURES_PROVIDER_SYMBOLS[compact])
        if _B3_MINI_FUTURE_RE.match(compact):
            aliases.append(f"{compact}.SA")
        if compact.endswith("USD"):
            aliases.extend([compact.replace("USD", "-USD"), compact.replace("USD", "USDT")])
        if re.match(r"^[A-Z]{4}(3|4|5|6|11)$", base) or re.match(r"^[A-Z]{4,5}34$", base):
            aliases.append(f"{base}.SA")

    return _dedupe_alias_symbols(aliases)


def _identity_forms(value) -> set[str]:
    raw = str(value or "").upper().strip()
    if not raw:
        return set()

    without_suffix = raw[:-3] if raw.endswith(".SA") else raw
    compact = without_suffix.replace("-USD", "USD")
    if compact.endswith("USDT"):
        compact = f"{compact[:-4]}USD"

    forms = {raw, without_suffix, compact}
    if compact.endswith("USD"):
        forms.add(compact.replace("USD", "-USD"))
        forms.add(compact.replace("USD", "USDT"))
    return {form for form in forms if form}


def _payload_matches_requested_symbol(payload, symbol: str, *, require_identity: bool = False) -> bool:
    if not isinstance(payload, dict):
        return False
    if is_bdr_symbol(symbol):
        if is_bdr_proxy_payload(payload):
            return False

    allowed: set[str] = set()
    for alias in [*_symbol_aliases(symbol), _response_symbol(symbol)]:
        allowed.update(_identity_forms(alias))

    identities: set[str] = set()
    for key in ("requested_symbol", "canonical_symbol", "symbol", "display_symbol", "provider_symbol", "reference_symbol", "exact_contract", "ticker"):
        identities.update(_identity_forms(payload.get(key)))

    source = str(payload.get("source") or "").lower().strip()
    snapshot_sources = {"snapshot", "last_good_snapshot", "stale_last_good_snapshot"}
    if require_identity and payload.get("identity_preserved") is not True and source not in snapshot_sources:
        return False
    if not identities:
        return not require_identity
    return bool(allowed.intersection(identities))


def _quote_identity_rank(payload: dict) -> int:
    if payload.get("identity_preserved") is True and all(
        payload.get(field) not in (None, "")
        for field in ("requested_symbol", "canonical_symbol", "display_symbol", "provider_symbol", "asset_type", "market", "currency")
    ):
        return 0
    return 1


def _matching_quote_candidates(cached_payloads, symbol: str) -> list[dict]:
    candidates: list[dict] = []
    seen: set[int] = set()
    for alias in _symbol_aliases(symbol):
        candidate = cached_payloads.get(alias)
        if not isinstance(candidate, dict):
            continue
        if not _payload_matches_requested_symbol(candidate, symbol, require_identity=True):
            continue
        marker = id(candidate)
        if marker in seen:
            continue
        seen.add(marker)
        candidates.append(candidate)
    candidates.sort(key=_quote_identity_rank)
    return candidates


def _snapshot_master_context(symbol: str, source_payload: dict | None = None) -> dict:
    row = {}
    if source_payload and isinstance(source_payload.get("insight"), dict):
        row = dict(source_payload["insight"])
        panel = source_payload.get("strategic_panel")
        if isinstance(panel, dict):
            row = {**row, **panel, "strategic_panel": panel}
    else:
        row = get_snapshot_ticker(_symbol_aliases(symbol))
        if not isinstance(row, dict) or not isinstance(row.get("strategic_panel"), dict) or not row.get("strategic_panel"):
            canonical = canonical_symbol(symbol)
            panels = get_snapshot().get("strategic_panels", [])
            panel = next(
                (
                    item
                    for item in panels
                    if isinstance(item, dict)
                    and canonical_symbol(item.get("ticker") or item.get("symbol")) == canonical
                ),
                None,
            )
            if isinstance(panel, dict):
                row = {**(row or {}), **panel, "strategic_panel": panel}
    if not isinstance(row, dict):
        return {}
    row = attach_master_score_display_contract(dict(row))
    decision_envelope = build_decision_envelope(row)
    return _json_safe_payload({
        "master_score": row.get("master_score"),
        "master_score_raw": row.get("master_score_raw"),
        "master_score_source_scale": row.get("master_score_source_scale"),
        "decision_status": decision_envelope.get("decision_status"),
        "decision_envelope": decision_envelope,
        "master_direction": row.get("master_direction"),
        "master_conviction": row.get("master_conviction"),
        "master_confidence": row.get("master_confidence"),
        "master_summary": row.get("master_summary"),
        "master_reasoning": row.get("master_reasoning") if isinstance(row.get("master_reasoning"), dict) else {},
        "master_risk": row.get("master_risk"),
        "master_status": row.get("master_status"),
        "opinion_change_conditions": row.get("opinion_change_conditions") or [],
        "strategic_panel": row.get("strategic_panel") if isinstance(row.get("strategic_panel"), dict) else {},
        "strategic_panel_summary": row.get("strategic_panel_summary") or "",
        "institutional_flow": row.get("institutional_flow"),
        "recommended_action": row.get("recommended_action"),
        "radar_prioritization_score": row.get("radar_prioritization_score"),
        "radar_priority_score": row.get("radar_priority_score"),
        "radar_priority": row.get("radar_priority"),
        "radar_level": row.get("radar_level"),
        "radar_reason": row.get("radar_reason"),
        "radar_summary": row.get("radar_summary"),
        "radar_no_trade_now": bool(row.get("radar_no_trade_now")),
        "radar_blocked_reasons": row.get("radar_blocked_reasons") or [],
        "ranking_opportunity_score": row.get("ranking_opportunity_score"),
        "ranking_classification": row.get("ranking_classification"),
        "ranking_reason": row.get("ranking_reason"),
        "ranking_summary": row.get("ranking_summary"),
        "ranking_eligible": row.get("ranking_eligible"),
        "ranking_excluded_reasons": row.get("ranking_excluded_reasons") or [],
        "historical_confidence_score": row.get("historical_confidence_score"),
        "historical_confidence_label": row.get("historical_confidence_label"),
        "historical_sample_size": row.get("historical_sample_size"),
        "historical_win_rate": row.get("historical_win_rate"),
        "historical_context_match": row.get("historical_context_match"),
        "historical_reason": row.get("historical_reason"),
        "historical_warning": row.get("historical_warning"),
        "operational_status": row.get("operational_status"),
        "operational_ready": row.get("operational_ready"),
        "operational_score": row.get("operational_score"),
        "operational_blocks": row.get("operational_blocks") or [],
        "operational_warnings": row.get("operational_warnings") or [],
        "operational_summary": row.get("operational_summary"),
        "conviction_score": row.get("conviction_score"),
        "conviction_level": row.get("conviction_level"),
        "conviction_summary": row.get("conviction_summary"),
        "conviction_factors": row.get("conviction_factors") or [],
        "conviction_conflicts": row.get("conviction_conflicts") or [],
        "priority_score": row.get("priority_score"),
        "priority_level": row.get("priority_level"),
        "priority_rank": row.get("priority_rank"),
        "priority_summary": row.get("priority_summary"),
        "priority_factors": row.get("priority_factors") or [],
        "final_decision": row.get("final_decision"),
        "final_decision_score": row.get("final_decision_score"),
        "final_decision_summary": row.get("final_decision_summary"),
        "final_decision_reason": row.get("final_decision_reason"),
        "final_decision_blocks": row.get("final_decision_blocks") or [],
        "final_decision_confidence": row.get("final_decision_confidence"),
    })


def _is_blocked_public_symbol(symbol: str) -> bool:
    return any(alias in _PUBLIC_MARKET_BLOCKED_SYMBOLS for alias in _symbol_aliases(symbol))


def _numeric_close_values(ohlc):
    closes = []
    for row in ohlc or []:
        try:
            close = float(row.get("close") or 0)
        except (TypeError, ValueError):
            continue
        if close > 0:
            closes.append(close)
    return closes


def _optional_float(value) -> float | None:
    parsed = _safe_float(value, default=float("nan"))
    return parsed if math.isfinite(parsed) else None


def _ai_metric_component(ai_tools: dict, tool: str, symbol: str) -> dict:
    status = str(ai_tools.get("status") or "PENDING").upper()
    tools = ai_tools.get("tools") if isinstance(ai_tools, dict) else None
    rows = (tools.get(tool) or []) if isinstance(tools, dict) else []
    canonical = canonical_symbol(symbol)
    row = next(
        (
            item for item in rows
            if isinstance(item, dict)
            and canonical_symbol(item.get("canonical_symbol") or item.get("ticker") or item.get("symbol")) == canonical
        ),
        None,
    )
    if row is None:
        component_status = "PENDING" if status in {"PENDING", "REFRESHING"} else "INSUFFICIENT_DATA"
        return {"symbol": canonical, "status": component_status, "value": None, "label": None, "timeframe": "5m", "as_of": None, "source": None}
    freshness = str(row.get("freshness_status") or "READY").upper()
    component_status = "READY" if status == "READY" and freshness == "READY" else "STALE" if freshness in {"STALE", "HISTORICAL"} else status
    score = _optional_float(row.get("score"))
    timeframe = str(row.get("candle_timeframe") or "5m")
    as_of = row.get("as_of") or row.get("market_data_updated_at") or row.get("last_bar_at")
    updated_at = row.get("last_confirmed_at") or row.get("updated_at")
    source = row.get("source") or "on_demand_ai"
    if tool == "liquidity":
        liquidity_metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
        low = _optional_float(liquidity_metrics.get("lower_liquidity"))
        high = _optional_float(liquidity_metrics.get("upper_liquidity"))
        price = _optional_float(row.get("price"))
        valid_range = low is not None and high is not None and price is not None and price > 0 and low < high
        side = (
            "SELL_SIDE" if valid_range and low > price
            else "BUY_SIDE" if valid_range and high < price
            else "BOTH_SIDES" if valid_range
            else None
        )
        geometry_ready = valid_range and bool(as_of) and bool(source)
        if component_status != "READY" or not geometry_ready:
            if low is None or high is None:
                reason = "missing_liquidity_bounds"
            elif price is None or price <= 0:
                reason = "missing_reference_price"
            elif low >= high:
                reason = "invalid_liquidity_range"
            elif not as_of:
                reason = "missing_liquidity_timestamp"
            else:
                reason = "liquidity_not_ready"
            return {
                "symbol": canonical, "status": component_status if component_status != "READY" else "INSUFFICIENT_DATA",
                "value": None, "score": score, "label": "Liquidez indisponível — dados insuficientes",
                "side": None, "low": None, "high": None, "midpoint": None,
                "distance_from_price_pct": None, "timeframe": timeframe, "as_of": as_of,
                "updated_at": updated_at, "source": source,
                "reason": reason,
            }
        midpoint = round((low + high) / 2, 6)
        is_envelope = side == "BOTH_SIDES"
        return {
            "symbol": canonical, "status": "READY", "value": None, "score": score,
            "label": (
                "Liquidez vendedora acima do preço" if side == "SELL_SIDE"
                else "Liquidez compradora abaixo do preço" if side == "BUY_SIDE"
                else "Faixa de liquidez ao redor do preço"
            ),
            "side": side, "low": low, "high": high, "midpoint": midpoint,
            "distance_from_price_pct": round(((midpoint - price) / price) * 100, 4),
            "timeframe": timeframe, "as_of": as_of, "updated_at": updated_at,
            "source": source, "reason": "validated_liquidity_envelope" if is_envelope else "validated_liquidity_range",
        }
    if tool == "flow" and score is not None:
        label = "Comprador" if score >= 60 else "Vendedor" if score < 40 else "Neutro"
    else:
        label = row.get("state_label") or row.get("label") or row.get("state")
    return {
        "symbol": canonical, "status": component_status, "value": score, "label": label,
        "thresholds": {"seller_max": 39.999, "neutral_max": 59.999, "buyer_min": 60} if tool == "flow" else None,
        "timeframe": timeframe, "as_of": as_of, "updated_at": updated_at, "source": source,
    }


def _unsupported_crypto_market_component(symbol: str, component: str) -> dict:
    canonical = canonical_symbol(symbol)
    label = (
        "Fluxo não disponível para este ativo"
        if component == "flow"
        else "Liquidez não disponível para este ativo"
    )
    return {
        "symbol": canonical,
        "status": "UNSUPPORTED",
        "value": None,
        "score": None,
        "label": label,
        "timeframe": "5m",
        "as_of": None,
        "updated_at": None,
        "source": None,
        "reason": "provider_has_no_crypto_orderflow",
    }


def build_symbol_operational_view(
    symbol: str,
    timeframe: str,
    insight: dict,
    metrics: dict,
    *,
    chart: dict | None = None,
    daily_rows: list[dict] | None = None,
    ai_tools: dict | None = None,
) -> dict:
    """Canonical selected-symbol context consumed by the page without recomputation."""
    canonical = canonical_symbol(symbol)
    chart = chart or {}
    daily_rows = daily_rows or []
    daily_closes = _numeric_close_values(daily_rows)
    daily_as_of = public_chart_as_of(daily_rows)
    daily_status = public_daily_freshness_status(daily_rows, metrics.get("session_date"), required_count=15)
    daily_trend = _fallback_bias(daily_closes) if len(daily_closes) >= 15 else None
    intraday_summary = chart.get("summary") or {}
    intraday_trend = intraday_summary.get("trend_bias")
    is_crypto = symbol_category(canonical) == "Crypto"
    daily_age_sessions = public_daily_age_sessions(
        daily_rows,
        metrics.get("session_date"),
        continuous_market=is_crypto,
    )
    flow = (
        _unsupported_crypto_market_component(canonical, "flow")
        if is_crypto
        else _ai_metric_component(ai_tools or {}, "flow", canonical)
    )
    liquidity = (
        _unsupported_crypto_market_component(canonical, "liquidity")
        if is_crypto
        else _ai_metric_component(ai_tools or {}, "liquidity", canonical)
    )
    levels = metrics.get("levels") or {}
    intraday_rvol = metrics.get("intraday_rvol") or metrics.get("rvol") or {}
    daily_volume_ratio = metrics.get("volume_vs_daily_average") or {}
    sentiment = metrics.get("sentiment") or {}
    panel = insight.get("strategic_panel") if isinstance(insight.get("strategic_panel"), dict) else {}
    master_score = _optional_float(insight.get("master_score") if insight.get("master_score") is not None else insight.get("score"))
    confidence_raw = panel.get("master_confidence_pct")
    if confidence_raw is None:
        confidence_raw = (panel.get("master_score_block") or {}).get("confidence_pct")
    confidence = _optional_float(confidence_raw)
    rsi_metadata = insight.get("rsi_metadata") or {}
    trend_component = {
        "symbol": canonical, "value": daily_trend, "label": daily_trend,
        "status": daily_status, "timeframe": "1d", "as_of": daily_as_of,
        "data_as_of": daily_as_of, "session_date": metrics.get("session_date"),
        "freshness_status": daily_status, "age_sessions": daily_age_sessions,
        "source": "daily_candles",
        "reason": "daily_candles_older_than_session" if daily_status == "STALE" else None,
    }
    rsi_status = (
        daily_status
        if rsi_metadata.get("status") == "AVAILABLE" and daily_status != "READY"
        else "READY"
        if rsi_metadata.get("status") == "AVAILABLE"
        else rsi_metadata.get("status", "PENDING")
    )
    rsi_component = {
        "symbol": canonical, "value": insight.get("rsi"), "label": None,
        "status": rsi_status, "timeframe": "1d", "as_of": rsi_metadata.get("as_of"),
        "data_as_of": rsi_metadata.get("as_of") or daily_as_of,
        "session_date": metrics.get("session_date"),
        "freshness_status": rsi_status, "age_sessions": daily_age_sessions,
        "source": rsi_metadata.get("source"),
        "reason": "daily_candles_older_than_session" if rsi_status == "STALE" else rsi_metadata.get("reason"),
    }
    intraday_component = {"symbol": canonical, "value": intraday_trend, "label": intraday_trend, "status": "READY" if intraday_trend else "PENDING", "timeframe": (chart.get("rsi_metadata") or {}).get("timeframe") or "5m", "as_of": intraday_summary.get("as_of"), "source": "intraday_chart"}

    direction_votes = [
        str(daily_trend or "").lower() if trend_component["status"] == "READY" else "",
        str(intraday_trend or "").lower() if intraday_component["status"] == "READY" else "",
        str(flow.get("label") or "").lower() if flow.get("status") == "READY" else "",
    ]
    bullish_votes = sum(value in {"alta", "bullish", "comprador"} for value in direction_votes)
    bearish_votes = sum(value in {"baixa", "bearish", "vendedor"} for value in direction_votes)
    technical_bias = "BULLISH" if bullish_votes >= 2 and bullish_votes > bearish_votes else "BEARISH" if bearish_votes >= 2 and bearish_votes > bullish_votes else "MIXED"
    technical_bias_component = {
        "symbol": canonical, "value": technical_bias,
        "label": "Comprador" if technical_bias == "BULLISH" else "Vendedor" if technical_bias == "BEARISH" else "Misto",
        "status": "READY" if trend_component["status"] == "READY" and intraday_component["status"] == "READY" else "PARTIAL",
        "timeframe": "D1+5m", "as_of": intraday_summary.get("as_of") or daily_as_of,
        "source": "selected_symbol_components",
    }

    score_components = {
        "trend_d1": trend_component,
        "rsi_d1": rsi_component,
        "intraday_direction": intraday_component,
        "flow": flow,
        "sentiment": sentiment,
        "intraday_rvol": intraday_rvol,
        "levels": levels,
    }
    if is_crypto:
        # Book/order-flow liquidity is an explicit unsupported input for the
        # crypto operational score, not a missing value or an implicit zero.
        score_components["liquidity"] = liquidity
    used_components = [name for name, payload in score_components.items() if str(payload.get("status") or "").upper() == "READY"]
    unsupported_components = [
        name for name, payload in score_components.items()
        if str(payload.get("status") or "").upper() == "UNSUPPORTED"
    ]
    missing_components = [
        name for name in score_components
        if name not in used_components and name not in unsupported_components
    ]
    eligible_count = len(score_components) - len(unsupported_components)
    completeness = round(len(used_components) / eligible_count, 4) if eligible_count else 0.0
    score_status = (
        "READY"
        if master_score is not None and not missing_components and not unsupported_components
        else "PARTIAL"
        if master_score is not None
        else "PENDING"
    )
    master_score_component = {
        "symbol": canonical, "value": master_score, "status": score_status,
        "label": "Score Mestre" if score_status == "READY" else "Score técnico parcial" if score_status == "PARTIAL" else "Score indisponível",
        "used_components": used_components, "missing_components": missing_components,
        "unsupported_components": unsupported_components,
        "data_completeness": completeness, "timeframe": "D1+5m",
        "as_of": flow.get("as_of") or intraday_summary.get("as_of"), "source": "on_demand_ai",
    }

    components = {
        "trend_d1": trend_component,
        "rsi_d1": rsi_component,
        "intraday_rvol": intraday_rvol,
        "sentiment": sentiment,
        "flow": flow,
        "liquidity": liquidity,
        "levels": levels,
    }
    pending = [
        {"component": component, "status": payload.get("status") or "PENDING", "reason": payload.get("reason") or "not_confirmed"}
        for component, payload in components.items()
        if str(payload.get("status") or "PENDING").upper() != "READY"
    ]
    required_for_execution = {"trend_d1", "rsi_d1", "intraday_rvol", "flow", "liquidity", "levels"}
    operational_blocks = [item for item in pending if item["component"] in required_for_execution]
    decision = "WAIT" if operational_blocks else str(insight.get("final_decision") or panel.get("recommended_action") or "WAIT").upper()
    return {
        "symbol": canonical,
        "canonical_symbol": canonical,
        "timeframe": str(timeframe or "1D").upper(),
        "session_date": metrics.get("session_date"),
        "as_of": intraday_summary.get("as_of") or metrics.get("as_of"),
        "updated_at": metrics.get("updated_at"),
        "source": "selected_symbol_bundle",
        "timeframes": {"chart_data": intraday_component["timeframe"], "operational": "5m", "structural": "1d"},
        "technical_context": {
            "technical_bias": technical_bias_component, "trend_d1": trend_component,
            "rsi_d1": rsi_component, "intraday_direction_5m": intraday_component,
            "institutional_flow": flow,
        },
        "operational_context": {
            "volume_vs_daily_average": daily_volume_ratio,
            "intraday_rvol": intraday_rvol, "rvol": intraday_rvol,
            "sentiment": sentiment, "liquidity": liquidity,
            "levels": levels, "master_score": master_score_component,
        },
        "pending_components": pending,
        "operational_blocks": operational_blocks,
        "decision": decision,
        "decision_reason": "operational_blocks" if operational_blocks else panel.get("final_decision_reason"),
        "confidence": None if operational_blocks else confidence,
        "confidence_status": "NOT_CONFIRMED" if operational_blocks or confidence is None else "READY",
        "conviction": None if operational_blocks else _optional_float(insight.get("conviction_score")),
        "conviction_status": "NOT_CALCULATED" if operational_blocks or insight.get("conviction_score") is None else "READY",
        "risk": insight.get("master_risk") or (panel.get("risk_block") or {}).get("level"),
        "levels": [] if str(levels.get("status")) != "READY" else levels.get("items") or [],
    }


def _market_metrics_contract(
    symbol: str,
    timeframe: str,
    quote: dict,
    chart: dict,
    news: dict | None = None,
    insight: dict | None = None,
    *,
    daily_rows: list[dict] | None = None,
    intraday_5m_rows: list[dict] | None = None,
    ai_tools: dict | None = None,
) -> dict:
    """Cache-only metrics; absence is explicit instead of a UI baseline."""
    canonical = canonical_symbol(symbol)
    is_crypto = symbol_category(canonical) == "Crypto"
    volume = _safe_float(quote.get("volume"), 0.0)
    average = _safe_float(quote.get("average_volume") or quote.get("avg_volume"), 0.0)
    daily_ratio_ready = volume > 0 and average > 0 and _payload_matches_requested_symbol(quote, canonical, require_identity=False)
    daily_ratio = round(volume / average, 4) if daily_ratio_ready else None
    as_of = quote.get("quote_time") or (chart.get("summary") or {}).get("as_of")
    zones = [zone for zone in chart.get("zones", []) if isinstance(zone, dict)]
    level_status = next((str(zone.get("status")) for zone in zones if zone.get("status") not in (None, "READY")), "READY" if zones else "PENDING")
    micro_support = next((_optional_float(zone.get("price")) for zone in zones if zone.get("kind") == "support" and zone.get("status") == "INSUFFICIENT_SEPARATION"), None)
    micro_resistance = next((_optional_float(zone.get("price")) for zone in zones if zone.get("kind") == "resistance" and zone.get("status") == "INSUFFICIENT_SEPARATION"), None)
    micro_range = None
    if micro_support is not None and micro_resistance is not None and micro_support < micro_resistance:
        micro_zone = next((zone for zone in zones if zone.get("status") == "INSUFFICIENT_SEPARATION"), {})
        micro_range = {
            "low": micro_support, "high": micro_resistance,
            "timeframe": micro_zone.get("micro_timeframe") or micro_zone.get("timeframe"),
            "status": "NON_OPERATIONAL", "reason": "insufficient_separation",
            "as_of": micro_zone.get("as_of") or (chart.get("summary") or {}).get("as_of"),
        }
    items = (news or {}).get("items") or []
    historical_at = next((item.get("published_at") or item.get("published") or item.get("date") for item in items if isinstance(item, dict)), None)
    volume_vs_daily_average = {
        "symbol": canonical, "current_volume": volume if volume > 0 else None,
        "daily_average_volume": average if average > 0 else None,
        "ratio": daily_ratio, "percent": round(daily_ratio * 100, 1) if daily_ratio is not None else None,
        "label": "Volume atual / média diária", "status": "READY" if daily_ratio_ready else "INSUFFICIENT_DATA",
        "method": "provider_full_day_average", "informational_only": True,
        "reason": None if daily_ratio_ready else "daily_average_unavailable", "as_of": quote.get("quote_time"),
        "source": quote.get("source") or "quote_cache",
    }
    # Same-UTC-bucket median RVOL is asset-agnostic: a stock's 14:05 bucket simply has samples on
    # trading days only, which still yields >=7 over the 20d window. Gating this to crypto is the
    # last reason equities never got a comparable intraday RVOL (auditor blocked -> NEUTRAL for all).
    intraday_rvol = build_crypto_intraday_rvol_contract(canonical, intraday_5m_rows)
    news_status = str((news or {}).get("data_status") or "").upper()
    fresh_items = [
        item for item in items
        if isinstance(item, dict) and (item.get("freshness_bucket") in {"today", "yesterday"} or not item.get("is_stale"))
    ]
    classified_items = [item for item in fresh_items if item.get("impact") in {"bullish", "bearish", "neutral"}]
    if classified_items:
        bull_count = sum(1 for item in classified_items if item.get("impact") == "bullish")
        bear_count = sum(1 for item in classified_items if item.get("impact") == "bearish")
        neutral_count = sum(1 for item in classified_items if item.get("impact") == "neutral")
        if bull_count > bear_count and bull_count > 0:
            s_val, s_lbl = "bullish", "Otimista"
        elif bear_count > bull_count and bear_count > 0:
            s_val, s_lbl = "bearish", "Pessimista"
        elif bull_count == 0 and bear_count == 0:
            s_val, s_lbl = "neutral", "Neutro"
        else:
            s_val, s_lbl = "mixed", "Misto"
        sentiment_status = "READY"
        sentiment_reason = None
        sentiment_value = s_val
        sentiment_label = s_lbl
        sentiment_components = {
            "bullish_count": bull_count,
            "bearish_count": bear_count,
            "neutral_count": neutral_count,
            "classified_total": len(classified_items),
            "missing_impact_count": len(fresh_items) - len(classified_items),
            "total_fresh": len(fresh_items),
        }
    else:
        sentiment_status = (
            "UNSUPPORTED"
            if is_crypto and news_status in {"UNSUPPORTED", "HISTORICAL", "STALE", "EMPTY"}
            else "INSUFFICIENT_DATA"
        )
        sentiment_reason = (
            "no_current_crypto_news_sentiment"
            if sentiment_status == "UNSUPPORTED"
            else "no_classified_sentiment"
            if fresh_items
            else "no_fresh_sentiment_source"
        )
        sentiment_value = None
        sentiment_label = "Sentimento atual indisponível"
        sentiment_components = {
            "bullish_count": 0,
            "bearish_count": 0,
            "neutral_count": 0,
            "classified_total": 0,
            "missing_impact_count": len(fresh_items),
            "total_fresh": len(fresh_items),
        }
    metrics = {
        "symbol": _response_symbol(canonical), "canonical_symbol": canonical,
        "provider_symbol": quote.get("provider_symbol") or provider_symbol(canonical), "timeframe": str(timeframe or "1D").upper(),
        "asset_class": "crypto" if is_crypto else quote.get("asset_class"),
        "market_schedule": "24x7" if is_crypto else quote.get("market_schedule"),
        "session_timezone": "UTC" if is_crypto else quote.get("session_timezone") or quote.get("timezone"),
        "market_status": "OPEN" if is_crypto else quote.get("market_status") or quote.get("market_state"),
        "session_date": str(as_of)[:10] if as_of else None, "as_of": as_of,
        "updated_at": quote.get("updated_at") or quote.get("quote_time"),
        "source": quote.get("source") or "quote_cache", "status": "PARTIAL",
        "data_quality": "VALID" if daily_ratio_ready else "PARTIAL",
        "volume_vs_daily_average": volume_vs_daily_average,
        "intraday_rvol": intraday_rvol,
        # Backwards-compatible key with corrected semantics: this is now the
        # operational intraday contract, never the daily informational ratio.
        "rvol": intraday_rvol,
        "sentiment": {"symbol": canonical, "value": sentiment_value, "label": sentiment_label, "status": sentiment_status, "reason": sentiment_reason, "last_historical_source_at": historical_at, "source": "news_impact_aggregation", "timeframe": str(timeframe or "1D").upper(), "as_of": (chart.get("summary") or {}).get("as_of"), "components": sentiment_components},
        "levels": {"status": level_status, "items": zones, "micro_range": micro_range, "as_of": (chart.get("summary") or {}).get("as_of")},
        "liquidity": (
            _unsupported_crypto_market_component(canonical, "liquidity")
            if is_crypto
            else {"status": "PENDING", "value": None, "label": "Calculando liquidez…", "as_of": None}
        ),
    }
    metrics["operational_view"] = build_symbol_operational_view(
        canonical, timeframe, insight or {}, metrics, chart=chart, daily_rows=daily_rows, ai_tools=ai_tools,
    )
    metrics["liquidity"] = metrics["operational_view"]["operational_context"]["liquidity"]
    return metrics


def _gate_pending_operational_levels(insight: dict, metrics: dict) -> dict:
    """Do not let an incomplete/micro range leak an entry into the panel."""
    if not isinstance(insight, dict) or str((metrics.get("levels") or {}).get("status")) == "READY":
        return insight
    panel = insight.get("strategic_panel")
    if not isinstance(panel, dict):
        return insight
    blocked = {**panel}
    for key in ("entry_reference", "stop", "target", "support", "resistance", "operational_zone"):
        blocked[key] = None
    blocked["operational_levels"] = {}
    blocked["operational_levels_block"] = {"status": (metrics.get("levels") or {}).get("status"), "levels": {}}
    blocked["recommended_action"] = "AGUARDAR"
    blocked["operational_blocks"] = (metrics.get("operational_view") or {}).get("operational_blocks") or []
    return {**insight, "strategic_panel": blocked}


def _safe_float(value, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _json_safe_payload(value):
    if isinstance(value, dict):
        return {key: _json_safe_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_payload(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _has_usable_quote_payload(payload, allow_stale: bool = False) -> bool:
    return is_usable_quote_payload(payload, allow_stale=allow_stale)


def _parse_payload_timestamp(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            timestamp = float(value)
            if timestamp > 10_000_000_000:
                timestamp /= 1000.0
            return timestamp if math.isfinite(timestamp) and timestamp > 0 else None
        text = str(value).strip()
        if not text:
            return None
        if re.fullmatch(r"\d+(\.\d+)?", text):
            timestamp = float(text)
            if timestamp > 10_000_000_000:
                timestamp /= 1000.0
            return timestamp if math.isfinite(timestamp) and timestamp > 0 else None
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except Exception:
        return None


def _quote_age_seconds(payload) -> float | None:
    if not isinstance(payload, dict):
        return None
    explicit_age = _safe_float(payload.get("cache_age_seconds"), default=-1.0)
    if explicit_age >= 0:
        return explicit_age
    for key in (
        "market_data_updated_at",
        "quote_time",
        "provider_timestamp",
        "timestamp",
        "updated_at",
        "last_seen_at",
        "created_at",
    ):
        parsed = _parse_payload_timestamp(payload.get(key))
        if parsed:
            return max(0.0, datetime.now(timezone.utc).timestamp() - parsed)
    return None


def _quote_needs_background_refresh(payload) -> bool:
    if not isinstance(payload, dict):
        return True
    price = _safe_float(payload.get("price"))
    if price <= 0:
        return True
    source = str(payload.get("source") or "").lower()
    status = str(payload.get("quote_status") or "").lower()
    if payload.get("stale") is True:
        return True
    if status in {"empty", "stale", "stale_chart", "reference"}:
        return True
    if "stale" in source or "fallback" in source or source == "empty":
        return True
    age = _quote_age_seconds(payload)
    return bool(age is not None and age > 180)


def _is_quote_fallback_chart(ohlc) -> bool:
    return bool(ohlc) and all(row.get("source") == "quote_cache_fallback" for row in ohlc or [])


def _fallback_bias(closes):
    if len(closes) < 2:
        return "neutro"

    latest = closes[-1]
    first = closes[0]
    short_window = closes[-min(len(closes), 8) :]
    short_avg = sum(short_window) / len(short_window)
    if latest >= short_avg and latest >= first:
        return "alta"
    if latest < short_avg and latest < first:
        return "baixa"
    return "neutro"


def _fallback_score(closes, rsi):
    if not closes:
        return None
    bias = _fallback_bias(closes)
    base = 5.0
    if rsi is not None:
        base += (float(rsi) - 50) / 12
    if bias == "alta":
        base += 1.0
    elif bias == "baixa":
        base -= 1.0
    return round(max(1.0, min(10.0, base)), 1)


def _resolve_cached_quote(cached_payloads, symbol: str, chart_quote_cache: dict | None = None):
    candidates = _matching_quote_candidates(cached_payloads, symbol)
    for candidate in candidates:
        if _has_usable_quote_payload(candidate, allow_stale=False) and not _quote_needs_background_refresh(candidate):
            payload = {**candidate, "symbol": _response_symbol(symbol)}
            if payload.get("source") is None:
                payload = {**payload, "source": "market_cache"}
            payload["quote_status"] = classify_quote_payload(payload)
            return with_quote_diagnostics(payload) or payload

    for candidate in candidates:
        if _has_usable_quote_payload(candidate, allow_stale=True):
            payload = {**candidate, "symbol": _response_symbol(symbol)}
            if payload.get("source") is None:
                payload = {**payload, "source": "market_cache_stale"}
            payload["quote_status"] = classify_quote_payload(payload)
            payload["stale"] = True
            return with_quote_diagnostics(payload) or payload

    for candidate in cached_payloads.values():
        if not isinstance(candidate, dict):
            continue
        if not _payload_matches_requested_symbol(candidate, symbol, require_identity=True):
            continue
        if _has_usable_quote_payload(candidate, allow_stale=True):
            payload = {**candidate, "symbol": _response_symbol(symbol)}
            if payload.get("source") is None:
                payload = {**payload, "source": "market_cache_alias_fallback"}
            payload["quote_status"] = classify_quote_payload(payload)
            payload["stale"] = True
            return with_quote_diagnostics(payload) or payload

    snapshot_payload = get_cached_quote_payload(symbol)
    if _payload_matches_requested_symbol(
        snapshot_payload,
        symbol,
        require_identity=True,
    ) and _has_usable_quote_payload(snapshot_payload, allow_stale=True):
        payload = {**snapshot_payload, "symbol": _response_symbol(symbol)}
        payload["quote_status"] = classify_quote_payload(payload)
        return with_quote_diagnostics(payload) or payload

    # Valid, unblocked, and nothing cached: the symbol is outside the warmup universe.
    # Enqueue it in the background so the next poll serves real data instead of
    # reporting "sem cotação" forever. Never a provider call on the request thread.
    schedule_quote_warmup(symbol)
    return empty_quote_payload(_response_symbol(symbol))


def _quote_from_chart_cache(symbol: str, chart_quote_cache: dict | None = None):
    cache_key = _response_symbol(symbol)
    if chart_quote_cache is not None and cache_key in chart_quote_cache:
        return chart_quote_cache[cache_key]

    rows = load_public_chart_rows(_symbol_aliases(symbol), "1D", scope="quote_chart_fallback")
    if not rows:
        if chart_quote_cache is not None:
            chart_quote_cache[cache_key] = None
        return None

    valid_rows = []
    for row in rows:
        close = _safe_float((row or {}).get("close"))
        if close > 0:
            valid_rows.append(row)
    if not valid_rows:
        if chart_quote_cache is not None:
            chart_quote_cache[cache_key] = None
        return None

    latest = valid_rows[-1]
    previous = valid_rows[-2] if len(valid_rows) > 1 else valid_rows[0]
    price = _safe_float(latest.get("close"))
    # Same baseline contract as the loader: previous SESSION close, not the
    # previous 5-minute candle. Falls back to the previous row only when the
    # cached chart holds a single session.
    previous_close = previous_session_close(
        [row.get("time") for row in valid_rows],
        [_safe_float(row.get("close")) for row in valid_rows],
    )
    if previous_close is None:
        previous_close = _safe_float(previous.get("close"))
    change_contract = session_change(price, previous_close)
    volumes = [_safe_float(row.get("volume")) for row in valid_rows]
    volume = sum(value for value in volumes if value > 0)
    highs = [_safe_float(row.get("high")) for row in valid_rows]
    lows = [_safe_float(row.get("low")) for row in valid_rows]
    positive_highs = [value for value in highs if value > 0]
    positive_lows = [value for value in lows if value > 0]
    payload = {
        "symbol": _response_symbol(symbol),
        "price": round(price, 4),
        **change_contract,
        "volume": round(volume, 2) if volume > 0 else None,
        "high": round(max(positive_highs), 4) if positive_highs else round(price, 4),
        "low": round(min(positive_lows), 4) if positive_lows else round(price, 4),
        "market_data_updated_at": latest.get("time"),
        "provider_timestamp": latest.get("time"),
        "source": "chart_cache_fallback",
        "quote_status": "stale_chart",
        "stale": True,
    }
    payload = with_quote_diagnostics(payload) or payload
    if chart_quote_cache is not None:
        chart_quote_cache[cache_key] = payload
    return payload


def _resolve_quote_for_chart(symbol: str):
    aliases = _symbol_aliases(symbol)
    if not aliases:
        return None

    cached_payloads = cached_price_payloads(aliases, allow_stale=True)

    for alias in aliases:
        payload = cached_payloads.get(alias)
        if not isinstance(payload, dict):
            continue
        if not _payload_matches_requested_symbol(payload, symbol):
            continue
        price = _safe_float(payload.get("price"))
        if price > 0:
            return {**payload, "symbol": _response_symbol(symbol)}

    for payload in cached_payloads.values():
        if (
            isinstance(payload, dict)
            and _payload_matches_requested_symbol(payload, symbol, require_identity=True)
            and _safe_float(payload.get("price")) > 0
        ):
            return {**payload, "symbol": _response_symbol(symbol)}

    return None


def _interval_shape(interval: str) -> tuple[int, timedelta]:
    normalized = str(interval or "1D").upper().strip()
    if normalized == "1D":
        return 78, timedelta(minutes=5)
    if normalized == "1W":
        return 7, timedelta(days=1)
    if normalized == "1M":
        return 22, timedelta(days=1)
    if normalized == "3M":
        return 63, timedelta(days=1)
    if normalized == "6M":
        return 90, timedelta(days=2)
    if normalized == "YTD":
        return 120, timedelta(days=1)
    if normalized == "1Y":
        return 122, timedelta(days=3)
    return 156, timedelta(days=7)


def _fallback_chart_end(interval: str) -> datetime:
    normalized = str(interval or "1D").upper().strip()
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    if normalized != "1D":
        return now

    sao_paulo = ZoneInfo("America/Sao_Paulo")
    local_now = now.astimezone(sao_paulo)
    session_close = local_now.replace(hour=17, minute=55, second=0, microsecond=0)
    session_open = local_now.replace(hour=10, minute=0, second=0, microsecond=0)
    if local_now < session_open:
        session_close = session_close - timedelta(days=1)
        while session_close.weekday() >= 5:
            session_close = session_close - timedelta(days=1)
    elif local_now <= session_close:
        minute = (local_now.minute // 5) * 5
        session_close = local_now.replace(minute=minute, second=0, microsecond=0)
    while session_close.weekday() >= 5:
        session_close = session_close - timedelta(days=1)
    return session_close.astimezone(timezone.utc)


_SUPPORTED_CANDLE_INTERVALS = {"1M", "5M", "15M", "30M", "1H", "1D", "1WK"}
# The daily card must be daily: range "1D" means one day OF 5m candles, so the only
# honest source for a D1 read is an explicit daily-candle series.
_DAILY_CANDLE_INTERVAL = "@1D"


def _normalize_candle_interval(candles: str | None) -> str | None:
    """User-selected candle size ("1m"/"30m"/"1h"/"1d") -> loader token ("@1M").

    Namespaced with "@" because the range labels share spellings with candle sizes:
    bare "1M" is one month of daily candles, "@1M" is one minute.
    """
    token = str(candles or "").upper().strip().lstrip("@")
    return f"@{token}" if token in _SUPPORTED_CANDLE_INTERVALS else None


def _normalize_chart_interval(interval: str | None = "1D", range_value: str | None = None) -> str:
    raw_range = range_value if isinstance(range_value, str) else None
    raw_interval = interval if isinstance(interval, str) else None
    return str(raw_range or raw_interval or "1D").upper().strip()


def _build_quote_fallback_chart(symbol: str, interval: str):
    quote = _resolve_quote_for_chart(symbol)
    if not quote:
        return []

    price = _safe_float(quote.get("price"))
    if price <= 0:
        return []

    change = _safe_float(quote.get("change"))
    change_pct = _safe_float(quote.get("change_pct"))
    previous = price - change if change else 0.0
    if previous <= 0 and change_pct:
        previous = price / max(0.05, 1 + (change_pct / 100))
    if previous <= 0:
        direction = 1 if change_pct >= 0 else -1
        previous = price * (1 - direction * max(abs(change_pct), 0.08) / 100)

    count, step = _interval_shape(interval)
    volume = max(_safe_float(quote.get("volume")), 0.0)
    high_quote = _safe_float(quote.get("high"))
    low_quote = _safe_float(quote.get("low"))
    amplitude = max(abs(price - previous), price * 0.003)
    now = _fallback_chart_end(interval)
    rows = []
    last_close = previous

    for index in range(count):
        progress = index / max(count - 1, 1)
        trend = previous + ((price - previous) * progress)
        wave = math.sin(progress * math.pi * 4.0) * amplitude * 0.34
        close = price if index == count - 1 else max(0.01, trend + wave)
        open_price = last_close if index else max(0.01, close - ((price - previous) / max(count, 1)))
        spread = max(abs(close - open_price), price * 0.0012)
        high = max(open_price, close) + spread * 0.85
        low = max(0.01, min(open_price, close) - spread * 0.85)

        if index == count - 1:
            high = max(high, high_quote if high_quote > 0 else high, close)
            low = min(low, low_quote if low_quote > 0 else low, close)

        timestamp = now - step * (count - index - 1)
        rows.append(
            {
                "time": timestamp.isoformat(),
                "open": round(open_price, 6),
                "high": round(high, 6),
                "low": round(low, 6),
                "close": round(close, 6),
                "volume": round(volume / max(count, 1), 2),
                "source": "quote_cache_fallback",
            }
        )
        last_close = close

    return rows


@router.get("/market/quotes")
def public_quotes(symbols: str = Query(default="")):
    request_entries = []
    for part in symbols.split(","):
        if len(request_entries) >= 80:
            break
        raw = part.strip()
        if not raw:
            continue
        if is_ambiguous_crypto_symbol(raw):
            request_entries.append({"symbol": "", "payload": _invalid_quote_payload(raw, "ambiguous_symbol", "missing_quote_asset")})
            continue
        normalized = _normalize_public_symbol(raw)
        if not normalized:
            request_entries.append({"symbol": "", "payload": _invalid_quote_payload(raw, "invalid_symbol")})
            continue
        if _is_blocked_public_symbol(normalized):
            request_entries.append({"symbol": "", "payload": _invalid_quote_payload(normalized, "blocked_symbol")})
            continue
        request_entries.append({"symbol": normalized, "payload": None})

    limited_entries = request_entries
    limited_tickers = [entry["symbol"] for entry in limited_entries if entry.get("symbol")]
    cache_keys = _dedupe_alias_symbols(
        alias for symbol in limited_tickers for alias in _symbol_aliases(symbol)
    )
    cached_payloads = cached_price_payloads(cache_keys, allow_stale=True)
    chart_quote_cache: dict = {}
    items = []
    for entry in limited_entries:
        if entry.get("payload") is not None:
            items.append(entry["payload"])
            continue
        items.append(_resolve_cached_quote(cached_payloads, entry["symbol"], chart_quote_cache=chart_quote_cache))
    for entry, resolved in zip(limited_entries, items):
        quote_status = classify_quote_payload(resolved) if isinstance(resolved, dict) else "empty"
        record_cache_access(
            "quote",
            quote_status in {"valid", "stale", "reference"},
            "public_quotes",
        )

    return _json_safe_payload({"items": items, "count": len(items)})


@router.get("/market/indices")
def public_market_indices():
    return _json_safe_payload(build_public_indices_payload())


@router.get("/market/insight/{symbol}")
def public_market_insight(
    symbol: str,
    interval: str = "1D",
    candles: str | None = None,
    is_premium: bool = Depends(resolve_premium_entitlement),
):
    interval = _normalize_candle_interval(candles) or interval
    if is_ambiguous_crypto_symbol(symbol):
        return _invalid_insight_payload(symbol, "ambiguous_symbol", "missing_quote_asset", interval=interval)
    ticker = _normalize_public_symbol(symbol)
    if not ticker:
        return _invalid_insight_payload(symbol, "invalid_symbol", "invalid_symbol", interval=interval)
    response_symbol = _response_symbol(ticker)
    # The bundle queues selected-symbol hydration. This endpoint stays a
    # cache-only reader so legacy consumers can still receive a snapshot when
    # no selected-symbol request exists yet.
    selected_context = resolve_symbol_context(ticker, interval)
    on_demand = selected_context.get("analysis") if isinstance(selected_context.get("analysis"), dict) else {}
    on_demand_ready = selected_context.get("status") == "READY" and canonical_symbol(on_demand.get("symbol")) == canonical_symbol(ticker)
    analysis_known = bool(on_demand)
    # A first-ever request for a symbol has analysis_known=True (queued) but not
    # yet on_demand_ready — this used to drop straight to {} and silently omit
    # strategic_panel/score_0_10 even though the snapshot already has it, which
    # is why the panel was missing on a cold symbol until someone else warmed it.
    # Snapshot is always a safe fallback: it's the same data on_demand will
    # eventually converge to, just not yet hydrated for this specific request.
    if on_demand_ready:
        master_context = _snapshot_master_context(ticker, source_payload=on_demand)
    else:
        master_context = _snapshot_master_context(ticker)
    if _is_blocked_public_symbol(ticker):
        rsi_contract = build_public_rsi_contract(
            response_symbol,
            interval,
            [],
            empty_status="INSUFFICIENT_DATA",
            empty_reason="blocked_symbol",
        )
        return _gate_insight_for_entitlement({
            "symbol": response_symbol,
            "score": None,
            **master_context,
            **rsi_contract,
            "trend_bias": None,
            "signal": None,
            "summary": {"source": "blocked_symbol"},
        }, is_premium)
    ohlc = _load_chart_data_fast(ticker, interval)
    empty_reason = "b3_future_exact_chart_unavailable" if _is_b3_mini_future_symbol(ticker) else "empty_chart"
    if not ohlc:
        rsi_contract = build_public_rsi_contract(
            response_symbol,
            interval,
            [],
            empty_status="PENDING",
            empty_reason=empty_reason,
        )
        return _gate_insight_for_entitlement({
            "symbol": response_symbol,
            "score": None,
            **master_context,
            **rsi_contract,
            "trend_bias": None,
            "signal": None,
            "summary": {
                "ticker": response_symbol,
                "source": empty_reason,
                "fallback": True,
                "status": "empty",
                "provider_status": empty_reason,
            },
            "fallback": True,
            "status": "empty",
            "provider_status": empty_reason,
        }, is_premium)

    is_quote_fallback = _is_quote_fallback_chart(ohlc)
    # While selected-symbol work is pending, expose only chart-derived fields;
    # never ask the global snapshot engine to fill a decision-shaped gap.
    insight = (
        dict(master_context)
        if on_demand_ready
        else {}
        if analysis_known or is_quote_fallback
        else (build_chart_signal_payload(ticker, ohlc, interval=interval) or {})
    )
    summary = dict(insight.get("summary") or {})
    if is_quote_fallback:
        summary.update({"source": "quote_cache_fallback", "fallback": True, "confidence": "derived"})
    closes = _numeric_close_values(ohlc)
    rsi_contract = build_public_rsi_contract(response_symbol, interval, ohlc)
    rsi = rsi_contract["rsi"]
    trend_bias = summary.get("trend_bias") or insight.get("trend_bias") or _fallback_bias(closes)
    score = insight.get("score")
    if score is None:
        score = _fallback_score(closes, rsi)

    return _gate_insight_for_entitlement(_json_safe_payload({
        "symbol": response_symbol,
        "score": master_context.get("score", score),
        **master_context,
        **rsi_contract,
        # Candles are the current same-symbol source for direction. A global
        # snapshot may supply score/history, never overwrite this live read.
        "trend_bias": trend_bias,
        "signal": insight.get("signal") or trend_bias,
        "summary": summary,
    }), is_premium)


@router.get("/market/chart/{symbol}")
def public_market_chart(
    symbol: str,
    interval: str = "1D",
    range_value: str | None = Query(default=None, alias="range"),
    candles: str | None = None,
):
    candle_interval = _normalize_candle_interval(candles)
    ticker = _normalize_public_symbol(symbol)
    if is_ambiguous_crypto_symbol(symbol):
        return _empty_chart_payload(
            _safe_response_symbol(symbol),
            _normalize_chart_interval(interval, range_value),
            "ambiguous_symbol",
            status="ambiguous_symbol",
        )
    if not ticker:
        return _empty_chart_payload(
            _safe_response_symbol(symbol),
            _normalize_chart_interval(interval, range_value),
            "invalid_symbol",
            status="invalid_symbol",
        )
    response_symbol = _response_symbol(ticker)
    chart_interval = candle_interval or _normalize_chart_interval(interval, range_value)
    if _is_blocked_public_symbol(ticker):
        return _empty_chart_payload(response_symbol, chart_interval, "blocked_symbol")
    ohlc = _load_chart_data_fast(ticker, chart_interval)
    if not ohlc:
        reason = "b3_future_exact_chart_unavailable" if _is_b3_mini_future_symbol(ticker) else "empty_chart"
        return _empty_chart_payload(response_symbol, chart_interval, reason)

    is_quote_fallback = _is_quote_fallback_chart(ohlc)
    signals = []
    chart_signal = {} if is_quote_fallback else (build_chart_signal_payload(ticker, ohlc, interval=chart_interval) or {})
    if chart_signal:
        signals.append(chart_signal)

    overlays = build_chart_overlays(ticker, ohlc, signals, interval=chart_interval)
    summary = dict(overlays["summary"] or {})
    if is_quote_fallback:
        summary.update({"source": "quote_cache_fallback", "fallback": True, "confidence": "derived"})
    as_of = public_chart_as_of(ohlc)
    summary["ticker"] = response_symbol
    summary["interval"] = chart_interval
    summary["as_of"] = as_of
    # Compute candle metadata before levels: the range label "1D" contains 5m
    # candles and must not be published as the level timeframe.
    rsi_contract = build_public_rsi_contract(response_symbol, chart_interval, ohlc)
    zones = normalize_public_chart_zones(
        overlays.get("zones"),
        symbol=response_symbol,
        timeframe=(rsi_contract.get("rsi_metadata") or {}).get("timeframe") or chart_interval,
        rows=ohlc,
    )
    # Mission 68: per-timeframe RSI from the exact candle series shown, so the
    # chart chip / RSI panel follow the selected timeframe (insight.rsi stays D1).
    return _json_safe_payload({
        "ticker": response_symbol,
        "interval": chart_interval,
        "ohlc": ohlc,
        "series": overlays["series"],
        "markers": overlays["markers"],
        "zones": zones,
        "summary": summary,
        **rsi_contract,
    })


_PREMIUM_GATING_ENABLED = _os_premium_gate.getenv("STOCKNEWS_PREMIUM_GATING", "1").strip().lower() not in {"0", "false", "no", "off"}

_PREMIUM_INSIGHT_PREFIXES = (
    "master_",
    "strategic_",
    "radar_",
    "ranking_",
    "historical_",
    "operational_",
    "conviction_",
    "priority_",
    "final_decision",
    "decision_",
)


def _gate_insight_for_entitlement(payload: dict, is_premium: bool) -> dict:
    """Project an insight to its public contract at the HTTP trust boundary."""
    # Direct Python callers are trusted internal consumers; FastAPI always
    # resolves the dependency to a real bool for HTTP requests.
    if not isinstance(is_premium, bool) or is_premium or not _PREMIUM_GATING_ENABLED or not isinstance(payload, dict):
        return payload
    for key in list(payload):
        if key in {"institutional_flow", "recommended_action"} or key.startswith(_PREMIUM_INSIGHT_PREFIXES):
            payload[key] = None
    payload["premium_locked"] = True
    payload["access_status"] = "basic"
    return payload


def _gate_ai_tools_for_entitlement(payload: dict, is_premium: bool) -> dict:
    if not isinstance(is_premium, bool) or is_premium or not _PREMIUM_GATING_ENABLED:
        return payload
    return {"tools": {}, "status": "PREMIUM_LOCKED", "locked": True}


def _gate_bundle_for_entitlement(payload: dict, is_premium: bool) -> dict:
    """Redact premium bundle fields for anonymous/Básico requests.

    Premium = Trial/Pro (resolve_premium_entitlement); anonymous and
    Básico/free/expired keep only the public fields (quote, chart, news).
    Server-side gate -- client query/header/body values cannot force Pro.
    """
    if not isinstance(is_premium, bool) or is_premium or not _PREMIUM_GATING_ENABLED or not isinstance(payload, dict):
        return payload
    insight = payload.get("insight")
    if isinstance(insight, dict):
        _gate_insight_for_entitlement(insight, False)

    # The operational view is derived from premium AI components and could
    # otherwise reconstruct score, flow, liquidity and the final decision.
    market_metrics = payload.get("market_metrics")
    if isinstance(market_metrics, dict):
        market_metrics["operational_view"] = None
        market_metrics["liquidity"] = None

    payload["ai_tools"] = _gate_ai_tools_for_entitlement(payload.get("ai_tools"), False)
    payload["premium_locked"] = True
    payload["access_status"] = "basic"
    return payload


@router.get("/market/bundle/{symbol}")
def public_market_bundle(
    symbol: str,
    interval: str = "1D",
    limit: int = 6,
    range_value: str | None = Query(default=None, alias="range"),
    locale: str = "pt-BR",
    candles: str | None = None,
    is_premium: bool = Depends(resolve_premium_entitlement),
):
    chart_interval = _normalize_candle_interval(candles) or _normalize_chart_interval(interval, range_value)
    safe_limit = max(1, min(int(limit or 6), 20))
    if is_ambiguous_crypto_symbol(symbol):
        return _invalid_bundle_payload(symbol, chart_interval, safe_limit, "ambiguous_symbol", "missing_quote_asset", locale)
    ticker = _normalize_public_symbol(symbol)
    if not ticker:
        return _invalid_bundle_payload(symbol, chart_interval, safe_limit, "invalid_symbol", "invalid_symbol", locale)
    response_symbol = _response_symbol(ticker)
    # The endpoint remains cache-only: this starts workers and returns the best
    # cached view immediately. The client polls this one selected symbol.
    request_symbol_hydration(ticker, timeframe=chart_interval, locale=locale, news_limit=safe_limit)
    cached_payloads = cached_price_payloads(_symbol_aliases(ticker), allow_stale=True)
    quote = _resolve_cached_quote(cached_payloads, ticker)
    record_cache_access("quote", _has_usable_quote_payload(quote), "public_bundle")

    insight = public_market_insight(ticker, interval=chart_interval, is_premium=True)
    # The top card is labelled "RSI diário (D1)", so it must be computed on DAILY
    # candles. Range "1D" is one day of 5m candles -- using it here is what made the
    # card publish an intraday RSI under a daily label. Score/trend stay per-timeframe.
    if isinstance(insight, dict) and str(chart_interval).upper().strip() != _DAILY_CANDLE_INTERVAL:
        insight = {
            **insight,
            **build_public_rsi_contract(
                response_symbol,
                _DAILY_CANDLE_INTERVAL,
                _load_chart_data_fast(ticker, _DAILY_CANDLE_INTERVAL),
            ),
        }
    on_demand = get_symbol_analysis(ticker, chart_interval)
    # The override was removed because public_market_insight now fully structures the on_demand payload.
    statuses = hydration_status(ticker, timeframe=chart_interval, locale=locale)
    news = build_public_news_payload(
        response_symbol, limit=safe_limit, source="public_bundle", allow_fetch=False,
        schedule_warmup=True, locale=locale,
    )
    ai_tools = build_public_ai_tools_payload([ticker, response_symbol], timeframe=chart_interval)
    ai_status = str(ai_tools.get("status") or "PENDING")
    ai_status_map = {
        "READY": "READY", "PENDING": "PENDING", "REFRESHING": "REFRESHING",
        "HISTORICAL": "HISTORICAL", "STALE": "STALE", "STALE_DATA": "STALE",
        "EMPTY": "EMPTY", "NO_QUALIFIED_FINDING": "EMPTY", "INSUFFICIENT_DATA": "INSUFFICIENT_DATA",
        "PROVIDER_ERROR": "ERROR", "ERROR": "ERROR",
    }
    statuses["news"] = str(news.get("data_status") or statuses.get("news") or "PENDING")
    statuses["ai"] = ai_status_map.get(ai_status, ai_status)
    chart = public_market_chart(ticker, interval=chart_interval, range_value=None)
    daily_rows = _load_chart_data_fast(ticker, _DAILY_CANDLE_INTERVAL)
    # Comparable intraday RVOL needs a multi-day 5m series (@5M ~1mo) to find >=7 same-UTC-bucket
    # samples. Feeding stocks [] here is why "RVOL intraday comparável" was always indisponível for
    # equities -> auditor blocked -> every stock collapsed to the same NEUTRAL/AGUARDAR verdict.
    intraday_5m_rows = load_public_chart_rows(
        _symbol_aliases(ticker), "@5M",
        scope="public_bundle_crypto_rvol" if symbol_category(ticker) == "Crypto" else "public_bundle_rvol",
    )
    daily_closes = _numeric_close_values(daily_rows)
    if len(daily_closes) >= 15:
        insight = {**insight, "trend_bias": _fallback_bias(daily_closes)}
    market_metrics = _market_metrics_contract(
        ticker, chart_interval, quote, chart, news, insight,
        daily_rows=daily_rows, intraday_5m_rows=intraday_5m_rows, ai_tools=ai_tools,
    )
    insight = _gate_pending_operational_levels(insight, market_metrics)
    # LLM conclusion layer (non-blocking): the Score Mestre stays the verdict; this only adds a
    # per-asset written explanation. get_cached_or_schedule never blocks the request -- it returns
    # the cached prose or None and fills it in a daemon thread for the next refresh. On any failure
    # the field is simply absent and the panel renders its existing template.
    if isinstance(insight, dict):
        _sp = insight.get("strategic_panel") if isinstance(insight.get("strategic_panel"), dict) else {}
        _verdict = _sp.get("recommended_action") or insight.get("recommended_action")
        if _verdict:
            try:
                from app.ai.conclusion_generator import get_cached_or_schedule

                _llm = get_cached_or_schedule({
                    "symbol": response_symbol,
                    "trend_bias": insight.get("trend_bias"),
                    "signal": insight.get("signal"),
                    "rsi": insight.get("rsi"),
                    "change_pct": quote.get("change_pct"),
                    "master_verdict": _verdict,
                    "support": _sp.get("support"),
                    "resistance": _sp.get("resistance"),
                })
                if _llm:
                    insight = {**insight, "strategic_panel": {**_sp, "llm_conclusion": _llm}}
            except Exception:  # noqa: BLE001 -- never let the conclusion layer break the bundle
                pass
    _bundle_payload = _json_safe_payload({
        "symbol": response_symbol,
        "quote": quote,
        "insight": insight,
        "chart": chart,
        "news": news,
        "ai_tools": ai_tools,
        "market_metrics": market_metrics,
        "asset_class": market_metrics.get("asset_class"),
        "market_schedule": market_metrics.get("market_schedule"),
        "session_timezone": market_metrics.get("session_timezone"),
        "market_status": market_metrics.get("market_status"),
        "data_status": statuses,
        "hydration": {
            "status": on_demand.get("status") or "PENDING",
            "reason": on_demand.get("reason"),
            "started_at": on_demand.get("started_at"),
            "deadline_at": on_demand.get("deadline_at"),
            "retry_count": on_demand.get("retry_count") or 0,
            "missing_components": on_demand.get("missing_components") or [],
            "updated_at": on_demand.get("updated_at"),
        },
        "retry_after_seconds": 3 if any(value == "PENDING" or value == "REFRESHING" for value in statuses.values()) else None,
        "source": "cache_snapshot_bundle",
    })
    return _gate_bundle_for_entitlement(_bundle_payload, is_premium)


def _empty_chart_payload(symbol: str, interval: str, reason: str, *, status: str = "empty"):
    rsi_contract = build_public_rsi_contract(
        symbol, interval, [], empty_status="PENDING", empty_reason=reason
    )
    return {
        "ticker": symbol,
        "interval": interval,
        "ohlc": [],
        "series": [],
        "markers": [],
        "zones": [],
        "summary": {
            "ticker": symbol,
            "interval": interval,
            "as_of": None,
            "source": reason,
            "fallback": True,
            "status": status,
            "provider_status": reason,
        },
        "fallback": True,
        "status": status,
        "provider_status": reason,
        **rsi_contract,
    }


# Candle sizes an already-warmed range label serves, so asking for a candle interval
# never turns the request path into a provider call (routes are cache-only by
# contract -- see tests/test_http_provider_guard.py; the warmup worker fills the
# cache). "@1M" (one minute) has no warmed range and stays null until pre-warmed.
_CANDLE_INTERVAL_WARM_RANGE = {
    "@5M": "1D",
    "@30M": "1W",
    "@1H": "1M",
    "@1D": "3M",
    "@1WK": "ALL",
}


def _load_chart_data_fast(ticker: str, interval: str):
    rows = load_public_chart_rows(_symbol_aliases(ticker), interval)
    if not rows:
        warm_range = _CANDLE_INTERVAL_WARM_RANGE.get(str(interval or "").upper().strip())
        if warm_range:
            rows = load_public_chart_rows(_symbol_aliases(ticker), warm_range)
    if rows:
        return rows
    cache_key = "chart_exact_miss_b3_future" if _is_b3_mini_future_symbol(ticker) else "chart_exact_miss"
    record_cache_access(cache_key, False, "public_market_live")
    if not _is_b3_mini_future_symbol(ticker):
        try:
            from app.system.chart_warmup import request_on_demand_chart_warmup

            requested = str(interval or "1D").upper().strip()
            warm_range = _CANDLE_INTERVAL_WARM_RANGE.get(requested)
            request_on_demand_chart_warmup(ticker, tuple(value for value in (requested, warm_range) if value))
        except Exception:
            pass
    return []
