# =====================================================
# MARKET SNAPSHOT ENGINE
# =====================================================

import logging
from datetime import datetime, timezone

import pandas as pd

from app.ai.feature_hub import build_ai_payload_bundle
from app.ai.ai_market_pulse import market_pulse as build_market_pulse
from app.ai.ai_master_score import apply_master_scores_by_ticker, run_master_score
from app.ai.final_decision import enrich_final_decision_rows, final_decision_items
from app.ai.historical_confidence import (
    apply_historical_confidence_by_ticker,
    enrich_historical_confidence_rows,
    historical_confidence_items,
)
from app.ai.institutional_conviction import (
    apply_conviction_by_ticker,
    conviction_items,
    enrich_institutional_conviction_rows,
)
from app.ai.institutional_priority import (
    apply_priority_by_ticker,
    enrich_institutional_priority_rows,
    priority_items,
)
from app.ai.operational_rules import (
    apply_operational_rules_by_ticker,
    enrich_operational_rules_rows,
)
from app.ai.institutional_radar import enrich_institutional_radar_rows, institutional_radar_items
from app.ai.institutional_ranking import enrich_institutional_ranking_rows, institutional_ranking_items
from app.ai.strategic_panel import apply_strategic_panels_by_ticker, build_strategic_panels
from app.ai.institutional_auditor import (
    apply_audit_to_ai_tools,
    audit_index,
    audit_market_rows,
    summarize_audits,
)
from app.ai.trade_decision import summarize_trade_decision
from app.cache.signal_cache import get_all_signals
from app.cache.snapshot_cache import get_last_good_snapshot, get_snapshot, update_snapshot
from app.data.warm_data_pool import get_market_pool
from app.engine.engine_orchestrator import run_engine
from app.engine.indicators.vector_indicator_engine import compute_rsi
from app.services.snapshot_contract import is_actionable_snapshot_row as _contract_is_actionable_snapshot_row
from app.services.snapshot_contract import coerce_data_quality, data_quality_label, data_quality_score
from app.services.snapshot_contract import summarize_snapshot_rows
from app.services.institutional_consistency_audit import audit_institutional_consistency
from app.services.snapshot_runtime_status import attach_snapshot_runtime_status
from app.services.signal_history import store_signals
from app.system.system_metrics import (
    record_institutional_auditor_metrics,
    record_institutional_consistency_metrics,
    record_master_score_metrics,
    record_signal_quality_coverage,
)

logger = logging.getLogger("stocknewsbr.snapshot_engine")
AI_INPUT_LIMIT = 80
AI_OUTPUT_LIMIT = 20
LAST_GOOD_SIGNAL_LIMIT = 200
SNAPSHOT_SCHEMA_VERSION = "market-ai-snapshot-v1"
MARKET_SNAPSHOT_INTERVAL_SECONDS = 30
AI_SNAPSHOT_INTERVAL_SECONDS = 300
_FEATURE_SEED_FIELDS = {
    "price",
    "volume",
    "avg_volume",
    "rel_volume",
    "vwap",
    "rsi",
    "macd",
    "macd_signal",
    "macd_histogram",
    "adx",
    "atr_pct",
    "bb_width",
    "kc_width",
    "momentum",
    "change_pct",
    "data_quality",
    "market_data_updated_at",
    "last_bar_at",
}
_ACTIONABLE_SIGNALS = {"BUY", "SELL", "SHORT", "COVER"}
_BULLISH_ACTIONS = {"BUY", "COVER"}
_BEARISH_ACTIONS = {"SELL", "SHORT"}
_BLOCKED_DATA_QUALITIES = {
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


def _safe_score(row):
    try:
        return float(row.get("score", 0) or 0)
    except Exception:
        return 0.0


def _safe_master_score(row):
    try:
        return float(row.get("master_score", row.get("score", 0)) or 0)
    except Exception:
        return _safe_score(row)


def _normalize_pool_key(value: str | None) -> str:
    ticker = str(value or "").upper().strip()

    if not ticker:
        return ticker

    if ticker.endswith(".SA"):
        return ticker

    if ticker.endswith("USD") and "-" not in ticker:
        return ticker[:-3] + "-USD"

    if "." not in ticker and "-" not in ticker and ticker.endswith(("3", "4", "5", "6", "11", "34")):
        return f"{ticker}.SA"

    return ticker


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _has_positive_value(row, *keys: str) -> bool:
    for key in keys:
        if _safe_float(row.get(key), 0.0) > 0:
            return True
    return False


def _snapshot_signal_value(row) -> str:
    return str(row.get("trade_action") or row.get("signal") or row.get("action") or "").upper().strip()


def _has_blocking_reasons(row) -> bool:
    reasons = row.get("blocked_reasons") or row.get("warnings") or []
    if isinstance(reasons, str):
        return bool(reasons.strip())
    if isinstance(reasons, (list, tuple, set)):
        return any(str(reason).strip() for reason in reasons)
    return bool(reasons)


def _is_actionable_snapshot_row(row) -> bool:
    return _contract_is_actionable_snapshot_row(row)


def _apply_master_scores_to_ai_tools(ai_tools, master_score_rows):
    output = {}
    for tool, rows in (ai_tools or {}).items():
        safe_rows = rows if isinstance(rows, list) else []
        output[tool] = apply_master_scores_by_ticker(safe_rows, master_score_rows)
    return output


def _apply_data_quality(row):
    item = dict(row)
    if _has_positive_value(item, "price", "close", "last_price") and _has_positive_value(item, "volume", "last_volume"):
        item["data_quality"] = coerce_data_quality(item)
    else:
        item["data_quality"] = "score_only"
    item["data_quality_label"] = data_quality_label(item["data_quality"])
    item["data_quality_score"] = data_quality_score(item["data_quality"])
    item["last_updated"] = item.get("last_updated") or item.get("market_data_updated_at") or item.get("updated_at") or item.get("generated_at")
    item["is_stale"] = bool(item.get("stale") is True or item.get("is_stale") is True or item["data_quality"] == "stale")
    item["fallback_used"] = bool(item.get("fallback_used"))
    item["provider_error"] = item.get("provider_error")
    item["source"] = item.get("source") or "snapshot"
    return item


def _latest_or_default(series, default: float = 0.0) -> float:
    try:
        if series is None or len(series) == 0:
            return default
        value = series.iloc[-1]
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _macd_snapshot(close):
    try:
        if close is None or len(close) < 26:
            return 0.0, 0.0, 0.0
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_series = ema12 - ema26
        signal_series = macd_series.ewm(span=9, adjust=False).mean()
        macd_value = _latest_or_default(macd_series, 0.0)
        signal_value = _latest_or_default(signal_series, 0.0)
        return macd_value, signal_value, macd_value - signal_value
    except Exception:
        return 0.0, 0.0, 0.0


def _has_canonical_snapshot_fields(row) -> bool:
    if not isinstance(row, dict):
        return False
    if not _has_positive_value(row, "price", "close", "last_price"):
        return False
    if not _has_positive_value(row, "volume", "last_volume"):
        return False
    return _FEATURE_SEED_FIELDS.issubset(row.keys())


def _build_feature_seed(ticker: str, frame, signal_row):
    if frame is None or frame.empty:
        return dict(signal_row)

    try:
        data = frame.tail(80).copy().dropna(how="all")

        if len(data) < 20:
            return dict(signal_row)

        close = data["Close"].astype(float).dropna()
        high = data["High"].astype(float).dropna()
        low = data["Low"].astype(float).dropna()
        open_ = data["Open"].astype(float).dropna()
        volume = data["Volume"].astype(float).fillna(0.0)

        if len(close) < 20:
            return dict(signal_row)

        market_data_updated_at = None
        try:
            last_index = close.index[-1]
            if hasattr(last_index, "isoformat"):
                market_data_updated_at = last_index.isoformat()
            elif last_index is not None:
                market_data_updated_at = str(last_index)
        except Exception:
            market_data_updated_at = None

        price = _latest_or_default(close)
        prev_close = _latest_or_default(close.iloc[:-1], price)
        open_price = _latest_or_default(open_, price)
        high_price = _latest_or_default(high, price)
        low_price = _latest_or_default(low, price)
        last_volume = _latest_or_default(volume, 0.0)
        avg_volume = float(volume.tail(20).mean()) if len(volume) >= 20 else float(volume.mean())
        rel_volume = (last_volume / avg_volume) if avg_volume > 0 else 0.0
        change_pct = ((price - prev_close) / prev_close * 100.0) if prev_close else 0.0
        macd_value, macd_signal_value, macd_histogram = _macd_snapshot(close)

        typical_price = (high.tail(20) + low.tail(20) + close.tail(20)) / 3.0
        typical_volume = volume.tail(20)
        volume_sum = float(typical_volume.sum())
        vwap = float((typical_price * typical_volume).sum() / volume_sum) if volume_sum > 0 else price

        rsi = _latest_or_default(compute_rsi(close), 50.0)

        prev_close_series = close.shift(1).fillna(close)
        true_range = pd.concat(
            [
                (high - low).abs(),
                (high - prev_close_series).abs(),
                (low - prev_close_series).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = float(true_range.tail(14).mean()) if len(true_range) >= 14 else float(true_range.mean())
        atr_pct = (atr / price * 100.0) if price > 0 else 0.0

        ema20 = close.ewm(span=20, adjust=False).mean()
        mid20 = _latest_or_default(ema20, price)
        std20 = float(close.tail(20).std()) if len(close) >= 20 else 0.0
        bb_width = ((4.0 * std20) / mid20) if mid20 > 0 else 0.0
        kc_width = ((4.0 * atr) / mid20) if mid20 > 0 else 0.0

        five_back = _safe_float(close.iloc[-6], price) if len(close) >= 6 else prev_close
        twenty_back = _safe_float(close.iloc[-21], price) if len(close) >= 21 else prev_close
        momentum = ((price - five_back) / five_back * 100.0) if five_back else 0.0
        trend_20 = ((price - twenty_back) / twenty_back * 100.0) if twenty_back else 0.0

        recent_returns = close.pct_change().dropna().tail(14)
        positive_days = int((recent_returns > 0).sum()) if len(recent_returns) else 0
        directional_persistence = (positive_days / max(1, len(recent_returns)))
        adx_proxy = 10.0 + abs(trend_20) * 2.6 + max(rel_volume - 1.0, 0.0) * 8.0 + directional_persistence * 18.0
        adx_proxy = max(10.0, min(45.0, adx_proxy))

        enriched = dict(signal_row)
        enriched.update(
            {
                "ticker": ticker,
                "symbol": ticker,
                "price": round(price, 6),
                "prev_close": round(prev_close, 6),
                "open": round(open_price, 6),
                "high": round(high_price, 6),
                "low": round(low_price, 6),
                "volume": int(last_volume),
                "avg_volume": int(avg_volume),
                "rel_volume": round(rel_volume, 4),
                "vwap": round(vwap, 6),
                "rsi": round(rsi, 4),
                "macd": round(macd_value, 6),
                "macd_signal": round(macd_signal_value, 6),
                "macd_histogram": round(macd_histogram, 6),
                "adx": round(adx_proxy, 4),
                "atr_pct": round(atr_pct, 4),
                "bb_width": round(bb_width, 6),
                "kc_width": round(kc_width, 6),
                "momentum": round(momentum, 4),
                "change_pct": round(change_pct, 4),
                "data_quality": "priced" if price > 0 and last_volume > 0 else "score_only",
                "market_data_updated_at": market_data_updated_at,
                "last_bar_at": market_data_updated_at,
                "feature_confidence": 92,
                "trend": signal_row.get("trend", trend_20),
            }
        )
        return enriched
    except Exception:
        logger.exception("Snapshot feature enrichment failed for %s", ticker)
        return dict(signal_row)


def _enrich_signal_rows(signals):
    rows = [dict(row) for row in signals or [] if isinstance(row, dict)]
    if not rows:
        return []

    if all(_has_canonical_snapshot_fields(row) for row in rows):
        return [_apply_data_quality(row) for row in rows]

    pool = get_market_pool()

    if not pool:
        return [_apply_data_quality(row) for row in rows]

    enriched = []
    pool_keys = {str(key).upper().strip(): value for key, value in pool.items()}

    for row in rows:
        if _has_canonical_snapshot_fields(row):
            enriched.append(_apply_data_quality(row))
            continue

        ticker = str(row.get("ticker") or row.get("symbol") or "").upper().strip()
        frame = pool_keys.get(ticker)

        if frame is None:
            frame = pool_keys.get(_normalize_pool_key(ticker))

        if frame is None:
            enriched.append(_apply_data_quality(row))
            continue

        enriched.append(_build_feature_seed(ticker or _normalize_pool_key(ticker), frame, row))

    return enriched


def build_snapshot_payload(signals, source: str = "engine", stale: bool = False):
    base_rows = []

    for row in signals or []:
        if not isinstance(row, dict):
            continue

        item = dict(row)
        ticker = item.get("ticker") or item.get("symbol")

        if ticker:
            item["ticker"] = ticker
            item["symbol"] = ticker

        item["score"] = _safe_score(item)
        base_rows.append(item)

    enriched_rows = _enrich_signal_rows(base_rows)
    normalized = []

    for row in enriched_rows:
        item = dict(row)
        ticker = item.get("ticker") or item.get("symbol")

        if ticker:
            item["ticker"] = ticker
            item["symbol"] = ticker

        item["score"] = _safe_score(item)
        normalized.append(_apply_data_quality(item))

    generated_at = datetime.now(timezone.utc).isoformat()
    normalized.sort(key=_safe_score, reverse=True)
    ai_input_rows = normalized[:AI_INPUT_LIMIT]

    ai_bundle: dict[str, object] = {}
    try:
        ai_bundle = build_ai_payload_bundle(
            top_signals=ai_input_rows,
            ranking=ai_input_rows,
            limit=AI_OUTPUT_LIMIT,
        )
        ai_tools = ai_bundle.get("ai_tools") if isinstance(ai_bundle, dict) else {}
    except Exception:
        logger.exception("Snapshot AI payload build failed")
        ai_tools = {}

    pre_audit_pulse = build_market_pulse(normalized)
    snapshot_context = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "source": source,
        "stale": bool(stale),
        "generated_at": generated_at,
    }
    normalized = audit_market_rows(
        normalized,
        ai_tools=ai_tools,
        market_pulse=pre_audit_pulse,
        snapshot_context=snapshot_context,
    )
    audits = audit_index(normalized)
    ai_tools = apply_audit_to_ai_tools(ai_tools, audits)
    post_audit_pulse = build_market_pulse(normalized)
    master_score_rows = run_master_score(
        normalized,
        limit=AI_OUTPUT_LIMIT,
        ai_tools=ai_tools,
        market_pulse=post_audit_pulse,
    )
    normalized = apply_master_scores_by_ticker(normalized, master_score_rows)
    ai_tools = _apply_master_scores_to_ai_tools(ai_tools, master_score_rows)
    strategic_panel_rows = build_strategic_panels(
        master_score_rows,
        ai_tools=ai_tools,
        limit=AI_OUTPUT_LIMIT,
    )
    master_score_rows = apply_strategic_panels_by_ticker(master_score_rows, strategic_panel_rows)
    normalized = apply_strategic_panels_by_ticker(normalized, strategic_panel_rows)
    final_market_pulse = build_market_pulse(normalized)
    normalized, radar_metrics = enrich_institutional_radar_rows(
        normalized,
        ai_tools=ai_tools,
        market_pulse=final_market_pulse,
    )
    institutional_radar = institutional_radar_items(normalized, limit=AI_OUTPUT_LIMIT)
    normalized, ranking_metrics = enrich_institutional_ranking_rows(
        normalized,
        ai_tools=ai_tools,
        market_pulse=final_market_pulse,
    )
    normalized, historical_confidence_metrics = enrich_historical_confidence_rows(normalized)
    master_score_rows = apply_historical_confidence_by_ticker(master_score_rows, normalized)
    strategic_panel_rows = apply_historical_confidence_by_ticker(strategic_panel_rows, normalized)
    normalized, operational_rules_metrics = enrich_operational_rules_rows(
        normalized,
        ai_tools=ai_tools,
        market_pulse=final_market_pulse,
    )
    master_score_rows = apply_operational_rules_by_ticker(master_score_rows, normalized)
    strategic_panel_rows = apply_operational_rules_by_ticker(strategic_panel_rows, normalized)
    normalized, conviction_metrics = enrich_institutional_conviction_rows(
        normalized,
        ai_tools=ai_tools,
        market_pulse=final_market_pulse,
    )
    master_score_rows = apply_conviction_by_ticker(master_score_rows, normalized)
    strategic_panel_rows = apply_conviction_by_ticker(strategic_panel_rows, normalized)
    normalized, priority_metrics = enrich_institutional_priority_rows(
        normalized,
        ai_tools=ai_tools,
        market_pulse=final_market_pulse,
    )
    master_score_rows = apply_priority_by_ticker(master_score_rows, normalized)
    strategic_panel_rows = apply_priority_by_ticker(strategic_panel_rows, normalized)
    normalized, final_decision_metrics = enrich_final_decision_rows(
        normalized,
        ai_tools=ai_tools,
        market_pulse=final_market_pulse,
    )
    institutional_ranking = institutional_ranking_items(normalized, limit=AI_OUTPUT_LIMIT)
    institutional_radar = institutional_radar_items(normalized, limit=AI_OUTPUT_LIMIT)
    historical_confidences = historical_confidence_items(normalized, limit=AI_OUTPUT_LIMIT)
    institutional_convictions = conviction_items(normalized, limit=AI_OUTPUT_LIMIT)
    institutional_priorities = priority_items(normalized, limit=AI_OUTPUT_LIMIT)
    final_decisions = final_decision_items(normalized, limit=AI_OUTPUT_LIMIT)
    consistency_audit = audit_institutional_consistency(normalized, generated_at=generated_at)
    normalized.sort(key=_safe_master_score, reverse=True)
    record_signal_quality_coverage(normalized, source=f"snapshot:{source}")

    actionable_rows = [row for row in normalized if _is_actionable_snapshot_row(row)]
    signal_stats = summarize_snapshot_rows(normalized)
    bullish = signal_stats["actionable_bullish"]
    bearish = signal_stats["actionable_bearish"]
    priced_rows = [row for row in normalized if _has_positive_value(row, "price", "close", "last_price")]
    score_only_rows = [
        row
        for row in normalized
        if str(row.get("data_quality") or "").lower().strip() in _BLOCKED_DATA_QUALITIES
    ]
    stale_rows = [
        row
        for row in normalized
        if row.get("stale") is True
        or row.get("is_stale") is True
        or str(row.get("data_quality") or "").lower().strip() == "stale"
    ]
    data_status = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "source": source,
        "generated_at": generated_at,
        "stale": bool(stale),
        "market_snapshot_interval_seconds": MARKET_SNAPSHOT_INTERVAL_SECONDS,
        "ai_snapshot_interval_seconds": AI_SNAPSHOT_INTERVAL_SECONDS,
        "total_signals": len(normalized),
        "priced": len(priced_rows),
        "score_only": len(score_only_rows),
        "stale_rows": len(stale_rows),
        "actionable": len(actionable_rows),
        "bullish_candidates": signal_stats["bullish_candidates"],
        "bearish_candidates": signal_stats["bearish_candidates"],
        "actionable_bullish": signal_stats["actionable_bullish"],
        "actionable_bearish": signal_stats["actionable_bearish"],
        "blocked_signals": signal_stats["blocked_signals"],
        "watchlist_candidates": signal_stats["watchlist_candidates"],
        "master_approved": sum(1 for row in normalized if str(row.get("master_status") or "").upper() == "APPROVED"),
        "master_caution": sum(1 for row in normalized if str(row.get("master_status") or "").upper() == "CAUTION"),
        "master_blocked": sum(1 for row in normalized if str(row.get("master_status") or "").upper() == "BLOCKED"),
        "radar_generated": radar_metrics["generated"],
        "radar_promoted": radar_metrics["promoted"],
        "radar_discarded": radar_metrics["discarded"],
        "radar_blocked": radar_metrics["blocked"],
        "ranking_eligible": ranking_metrics["eligible"],
        "ranking_excluded": ranking_metrics["excluded"],
        "ranking_promoted": ranking_metrics["promoted"],
        "ranking_top": ranking_metrics["top_ranking"],
        "historical_confidence_average": historical_confidence_metrics["average_confidence_score"],
        "historical_confidence_without_sample": historical_confidence_metrics["signals_without_sample"],
        "operational_ready": operational_rules_metrics["ready"],
        "operational_caution": operational_rules_metrics["caution"],
        "operational_blocked": operational_rules_metrics["blocked"],
        "conviction_average": conviction_metrics["average_conviction"],
        "conviction_high": conviction_metrics["high_conviction"],
        "conviction_low": conviction_metrics["low_conviction"],
        "conviction_conflicts": conviction_metrics["conflicts_detected"],
        "priority_critical": priority_metrics["critical"],
        "priority_high": priority_metrics["high"],
        "priority_medium": priority_metrics["medium"],
        "priority_low": priority_metrics["low"],
        "final_decision_confirmed": final_decision_metrics["confirmed"],
        "final_decision_forming": final_decision_metrics["forming"],
        "final_decision_observe": final_decision_metrics["observe"],
        "final_decision_wait": final_decision_metrics["wait"],
        "final_decision_no_trade": final_decision_metrics["no_trade"],
        "institutional_consistency_issues": consistency_audit["issue_count"],
    }
    auditor_summary = summarize_audits(normalized)
    record_institutional_auditor_metrics(auditor_summary)
    record_master_score_metrics(master_score_rows)
    record_institutional_consistency_metrics(consistency_audit.get("metrics"))

    decision = summarize_trade_decision(master_score_rows)
    logger.info(
        "Snapshot decision | action=%s | confidence=%.1f | regime=%s | source=%s | stale=%s",
        decision.get("trade_action"),
        float(decision.get("trade_confidence", 0.0) or 0.0),
        decision.get("market_regime_state"),
        source,
        stale,
    )

    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "signals": normalized[:200],
        "leaders": normalized[:20],
        "master_scores": master_score_rows,
        "master_score": master_score_rows[0] if master_score_rows else {},
        "strategic_panels": strategic_panel_rows,
        "strategic_panel": strategic_panel_rows[0] if strategic_panel_rows else {},
        "strategic_panel_summary": strategic_panel_rows[0].get("strategic_panel_summary") if strategic_panel_rows else "",
        "institutional_radar": institutional_radar,
        "radar_metrics": radar_metrics,
        "institutional_ranking": institutional_ranking,
        "ranking_metrics": ranking_metrics,
        "historical_confidences": historical_confidences,
        "historical_confidence": historical_confidences[0] if historical_confidences else {},
        "historical_confidence_metrics": historical_confidence_metrics,
        "operational_rules": normalized[:AI_OUTPUT_LIMIT],
        "operational_rules_metrics": operational_rules_metrics,
        "institutional_convictions": institutional_convictions,
        "institutional_conviction": institutional_convictions[0] if institutional_convictions else {},
        "conviction_metrics": conviction_metrics,
        "institutional_priorities": institutional_priorities,
        "institutional_priority": institutional_priorities[0] if institutional_priorities else {},
        "priority_metrics": priority_metrics,
        "final_decisions": final_decisions,
        "final_decision": final_decisions[0] if final_decisions else {},
        "final_decision_metrics": final_decision_metrics,
        "institutional_consistency": consistency_audit,
        "institutional_consistency_metrics": consistency_audit.get("metrics", {}),
        "symbol_snapshots": {
            str(row.get("symbol") or row.get("ticker") or "").upper(): row
            for row in normalized[:200]
            if row.get("symbol") or row.get("ticker")
        },
        "ai_tools": ai_tools,
        "ai_architecture": {
            "version": "v4_mission_13",
            "official_ai_count": 9,
            "trend_ia_decision": "dedicated",
            "master_score_exposed_as_ai": False,
            "master_score_contract": "institutional_synthesis",
            "strategic_panel_contract": "ten_second_institutional_read",
            "institutional_radar_contract": "mission_17_prioritized_attention",
            "institutional_ranking_contract": "mission_18_opportunity_quality",
            "historical_confidence_contract": "mission_19_contextual_evidence",
            "operational_rules_contract": "mission_20_minimum_trade_conditions",
            "institutional_conviction_contract": "mission_21_evidence_alignment",
            "institutional_priority_contract": "mission_22_attention_queue",
            "final_decision_contract": "mission_23_operational_conclusion",
            "internal_engine_keys": ai_bundle.get("internal_engine_keys", []) if isinstance(ai_bundle, dict) else [],
        },
        "decision": decision,
        "market_pulse": final_market_pulse,
        "auditor": auditor_summary,
        "institutional_auditor": auditor_summary,
        "generated_at": generated_at,
        "market_snapshot_interval_seconds": MARKET_SNAPSHOT_INTERVAL_SECONDS,
        "ai_snapshot_interval_seconds": AI_SNAPSHOT_INTERVAL_SECONDS,
        "data_status": data_status,
        "source": source,
        "stale": bool(stale),
        "stats": {
            "total_signals": len(normalized),
            "candidates": len(normalized),
            "priced": len(priced_rows),
            "score_only": len(score_only_rows),
            "stale_rows": len(stale_rows),
            "actionable": len(actionable_rows),
            "bullish_candidates": signal_stats["bullish_candidates"],
            "bearish_candidates": signal_stats["bearish_candidates"],
            "actionable_bullish": signal_stats["actionable_bullish"],
            "actionable_bearish": signal_stats["actionable_bearish"],
            "blocked_signals": signal_stats["blocked_signals"],
            "watchlist_candidates": signal_stats["watchlist_candidates"],
            "bullish": bullish,
            "bearish": bearish,
            "radar_generated": radar_metrics["generated"],
            "radar_promoted": radar_metrics["promoted"],
            "radar_discarded": radar_metrics["discarded"],
            "radar_blocked": radar_metrics["blocked"],
            "ranking_eligible": ranking_metrics["eligible"],
            "ranking_excluded": ranking_metrics["excluded"],
            "ranking_promoted": ranking_metrics["promoted"],
            "ranking_top": ranking_metrics["top_ranking"],
            "historical_confidence_average": historical_confidence_metrics["average_confidence_score"],
            "historical_confidence_without_sample": historical_confidence_metrics["signals_without_sample"],
            "operational_ready": operational_rules_metrics["ready"],
            "operational_caution": operational_rules_metrics["caution"],
            "operational_blocked": operational_rules_metrics["blocked"],
            "conviction_average": conviction_metrics["average_conviction"],
            "conviction_high": conviction_metrics["high_conviction"],
            "conviction_low": conviction_metrics["low_conviction"],
            "conviction_conflicts": conviction_metrics["conflicts_detected"],
            "priority_critical": priority_metrics["critical"],
            "priority_high": priority_metrics["high"],
            "priority_medium": priority_metrics["medium"],
            "priority_low": priority_metrics["low"],
            "final_decision_confirmed": final_decision_metrics["confirmed"],
            "final_decision_forming": final_decision_metrics["forming"],
            "final_decision_observe": final_decision_metrics["observe"],
            "final_decision_wait": final_decision_metrics["wait"],
            "final_decision_no_trade": final_decision_metrics["no_trade"],
            "institutional_consistency_issues": consistency_audit["issue_count"],
        },
    }
    return attach_snapshot_runtime_status(payload)


def _get_last_good_signals():
    snapshot = get_last_good_snapshot() or get_snapshot()
    snapshot_signals = snapshot.get("signals", [])

    if isinstance(snapshot_signals, list) and snapshot_signals:
        return snapshot_signals[:LAST_GOOD_SIGNAL_LIMIT]

    return []


def generate_market_snapshot(signals=None, reuse_last_good_on_empty: bool = True):
    snapshot_source = "signal_argument" if signals is not None else "signal_cache"
    snapshot_stale = False

    try:
        if signals is not None:
            signal_rows = list(signals or [])
            if not signal_rows and reuse_last_good_on_empty:
                signal_rows = _get_last_good_signals()
                snapshot_source = "snapshot_fallback"
                snapshot_stale = bool(signal_rows)
        else:
            signal_rows = get_all_signals()

        if signals is None and not signal_rows:
            snapshot_source = "engine"
            signal_rows = run_engine()

        explicit_empty_request = signals is not None and not signal_rows and not reuse_last_good_on_empty
        if explicit_empty_request:
            payload = build_snapshot_payload([], source="empty", stale=True)
            update_snapshot(payload)
            return payload

        if not signal_rows:
            signal_rows = _get_last_good_signals()
            snapshot_source = "snapshot_fallback"
            snapshot_stale = bool(signal_rows)

        if not signal_rows:
            payload = build_snapshot_payload([], source="empty", stale=True)
            update_snapshot(payload)
            return payload

        store_signals(signal_rows)

        payload = build_snapshot_payload(
            signal_rows,
            source=snapshot_source,
            stale=snapshot_stale,
        )
        update_snapshot(payload)

        return payload

    except Exception as exc:
        logger.exception("Snapshot engine error: %s", exc)
        fallback_rows = _get_last_good_signals()

        if fallback_rows:
            payload = build_snapshot_payload(
                fallback_rows,
                source="exception_fallback",
                stale=True,
            )
            update_snapshot(payload)
            return payload

        payload = build_snapshot_payload([], source="exception", stale=True)
        update_snapshot(payload)
        return payload
