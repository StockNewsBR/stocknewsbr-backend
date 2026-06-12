# =====================================================
# STOCKNEWSBR AI MARKET RADAR
# Ultra Fast Scanner
# =====================================================

import logging

import pandas as pd

from app.ai.ai_radar import run_radar
from app.ai.institutional_radar import enrich_institutional_radar_rows, institutional_radar_items
from app.cache.snapshot_cache import get_snapshot_signals
from app.services.snapshot_contract import coerce_data_quality, data_quality_label, data_quality_score, is_actionable_snapshot_row

logger = logging.getLogger("stocknewsbr.market_radar")

MIN_ROWS = 100


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def detect_compression(df):

    try:

        if df is None or len(df) < MIN_ROWS:
            return 0

        high = df["High"]
        low = df["Low"]
        close = df["Close"]
        volume = df["Volume"]

        # -------------------------
        # TRUE RANGE
        # -------------------------

        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)

        atr = tr.rolling(14).mean()
        atr_base = atr.rolling(50).mean().iloc[-1]

        if not atr_base:
            return 0

        atr_ratio = atr.iloc[-1] / atr_base

        # -------------------------
        # NR7
        # -------------------------

        ranges = high - low
        nr7 = ranges.iloc[-1] == ranges.rolling(7).min().iloc[-1]

        # -------------------------
        # VOLUME
        # -------------------------

        vol_avg = volume.rolling(20).mean().iloc[-1]

        if not vol_avg:
            return 0

        vol_ratio = volume.iloc[-1] / vol_avg

        # -------------------------
        # NEAR HIGH
        # -------------------------

        recent_high = close.rolling(20).max().iloc[-2]
        near_high = close.iloc[-1] > recent_high * 0.97

        score = 0

        if atr_ratio < 0.8:
            score += 30

        if nr7:
            score += 25

        if vol_ratio > 1.3:
            score += 25

        if near_high:
            score += 20

        return score

    except Exception:

        logger.exception("Compression detection error")

        return 0


def _normalize_symbol(value):
    return str(value or "").upper().strip().replace(".SA", "").replace("-USD", "USD")


def analyze_symbol(symbol):

    try:
        normalized = _normalize_symbol(symbol)
        rows = [
            row
            for row in get_snapshot_signals()
            if _normalize_symbol(row.get("ticker") or row.get("symbol")) == normalized
            and is_actionable_snapshot_row(row)
        ]

        radar_rows = run_radar(rows, limit=1)

        if not radar_rows:
            return None

        radar = radar_rows[0]
        score = _safe_float(radar.get("score") or radar.get("radar_score") or 0)
        source = rows[0] if rows else {}

        if score < 60:
            return None

        return {
            "symbol": normalized,
            "radar_score": score,
            "radar_prioritization_score": source.get("radar_prioritization_score"),
            "radar_priority_score": source.get("radar_priority_score"),
            "radar_priority": source.get("radar_priority"),
            "radar_level": source.get("radar_level"),
            "radar_reason": source.get("radar_reason"),
            "radar_summary": source.get("radar_summary"),
            "master_score": source.get("master_score"),
            "master_direction": source.get("master_direction"),
            "master_status": source.get("master_status"),
            "strategic_panel": source.get("strategic_panel") if isinstance(source.get("strategic_panel"), dict) else {},
            "strategic_panel_summary": source.get("strategic_panel_summary") or "",
            "recommended_action": source.get("recommended_action"),
        }

    except Exception:

        logger.exception(f"Radar analysis error {symbol}")

        return None


def build_radar():

    results = []

    try:
        snapshot_rows = [row for row in get_snapshot_signals() if isinstance(row, dict)]
        enriched_rows, _metrics = enrich_institutional_radar_rows(snapshot_rows, record_metrics=True)
        actionable_rows = [
            row
            for row in institutional_radar_items(enriched_rows, limit=50)
            if is_actionable_snapshot_row(row)
        ]
        source_by_ticker = {
            _normalize_symbol(row.get("ticker") or row.get("symbol")): row
            for row in actionable_rows
            if isinstance(row, dict)
        }

        for row in actionable_rows:
            symbol = row.get("ticker") or row.get("symbol")
            if not symbol:
                continue
            source = source_by_ticker.get(_normalize_symbol(symbol), {})
            results.append(
                {
                    "symbol": _normalize_symbol(symbol),
                    "radar_score": _safe_float(row.get("score") or row.get("radar_score") or 0),
                    "radar_prioritization_score": source.get("radar_prioritization_score"),
                    "radar_priority_score": source.get("radar_priority_score"),
                    "radar_priority": source.get("radar_priority"),
                    "radar_level": source.get("radar_level"),
                    "radar_reason": source.get("radar_reason"),
                    "radar_summary": source.get("radar_summary"),
                    "radar_no_trade_now": bool(source.get("radar_no_trade_now")),
                    "radar_blocked_reasons": source.get("radar_blocked_reasons") or [],
                    "master_score": source.get("master_score"),
                    "master_direction": source.get("master_direction"),
                    "master_conviction": source.get("master_conviction"),
                    "master_confidence": source.get("master_confidence"),
                    "master_summary": source.get("master_summary"),
                    "master_risk": source.get("master_risk"),
                    "master_status": source.get("master_status"),
                    "strategic_panel": source.get("strategic_panel") if isinstance(source.get("strategic_panel"), dict) else {},
                    "strategic_panel_summary": source.get("strategic_panel_summary") or "",
                    "recommended_action": source.get("recommended_action"),
                    "state": row.get("state"),
                    "source": row.get("source") or "snapshot",
                    "data_quality": coerce_data_quality(row),
                    "data_quality_label": data_quality_label(coerce_data_quality(row)),
                    "data_quality_score": data_quality_score(coerce_data_quality(row)),
                    "last_updated": row.get("last_updated") or row.get("updated_at") or row.get("generated_at"),
                    "is_stale": bool(row.get("stale") is True or row.get("is_stale") is True or coerce_data_quality(row) == "stale"),
                    "fallback_used": bool(row.get("fallback_used")),
                    "provider_error": row.get("provider_error"),
                    "audit_status": row.get("audit_status"),
                    "audit_score": row.get("audit_score"),
                    "audit_confidence": row.get("audit_confidence"),
                    "audit_summary": row.get("audit_summary"),
                    "blocked_by_auditor": bool(row.get("blocked_by_auditor") is True),
                }
            )

    except Exception:

        logger.exception("Radar scanner error")

    results.sort(key=lambda x: _safe_float(x.get("radar_prioritization_score") or x.get("radar_priority_score") or x.get("radar_score")), reverse=True)

    return results
