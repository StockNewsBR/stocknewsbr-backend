# =====================================================
# RANKING SERVICE
# Fast + Crash Safe
# =====================================================

from __future__ import annotations

import logging
import os
import time

from fastapi import APIRouter, Depends

from app.ai.final_decision import ensure_final_decision_rows
from app.ai.historical_confidence import ensure_historical_confidence_rows
from app.ai.institutional_conviction import ensure_institutional_conviction_rows
from app.ai.institutional_priority import ensure_institutional_priority_rows
from app.ai.institutional_ranking import ensure_institutional_ranking_rows, institutional_ranking_items
from app.ai.operational_rules import ensure_operational_rules_rows
from app.cache.market_data_cache import get_market_data
from app.cache.snapshot_cache import get_snapshot_info, get_snapshot_signals
from app.config import SYMBOLS
from app.dependencies import require_active_plan
from app.services.score_display import attach_master_score_display_contract
from app.services.snapshot_contract import coerce_data_quality, data_quality_label, data_quality_score, is_actionable_snapshot_row
from app.system.system_metrics import current_provider_call_source

logger = logging.getLogger("stocknewsbr.ranking")

router = APIRouter(
    prefix="/ranking",
    tags=["Ranking"],
)

CACHE_TTL = 120
SNAPSHOT_MAX_AGE = 600
ALLOW_NETWORK_FALLBACK = str(
    os.getenv("RANKING_ALLOW_NETWORK_FALLBACK", "0")
).strip().lower() in {"1", "true", "yes", "on"}

_RANK_CACHE = {
    "data": [],
    "timestamp": 0.0,
    "snapshot_signature": "",
}

_ACTIONABLE_SIGNALS = {"BUY", "SELL", "SHORT", "COVER"}
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


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _has_positive_value(row: dict, *keys: str) -> bool:
    return any(_safe_float(row.get(key)) > 0 for key in keys)


def _signal_value(row: dict) -> str:
    return str(row.get("trade_action") or row.get("signal") or row.get("action") or "").upper().strip()


def _has_blocking_reasons(row: dict) -> bool:
    reasons = row.get("blocked_reasons") or row.get("warnings") or []
    if isinstance(reasons, str):
        return bool(reasons.strip())
    if isinstance(reasons, (list, tuple, set)):
        return any(str(item).strip() for item in reasons)
    return bool(reasons)


def _is_actionable_snapshot_row(row: dict) -> bool:
    if _signal_value(row) not in _ACTIONABLE_SIGNALS:
        return False
    if row.get("decision_ready") is False:
        return False
    if row.get("stale") is True or row.get("is_stale") is True:
        return False
    if str(row.get("data_quality") or "").lower().strip() in _BLOCKED_DATA_QUALITIES:
        return False
    for status_key in ("quote_status", "status", "provider_status", "market_data_status"):
        if str(row.get(status_key) or "").lower().strip() in _BLOCKED_DATA_QUALITIES:
            return False
    if row.get("provider_failed") is True or row.get("provider_error") is True:
        return False
    if _has_blocking_reasons(row):
        return False
    if not _has_positive_value(row, "price", "close", "last_price"):
        return False
    if not _has_positive_value(row, "volume", "last_volume"):
        return False
    return True


def calculate_rsi(series: pd.Series, period: int = 14):
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_ema(series: pd.Series, period: int):
    return series.ewm(span=period, adjust=False).mean()


def calculate_macd(series: pd.Series):
    ema12 = calculate_ema(series, 12)
    ema26 = calculate_ema(series, 26)

    macd = ema12 - ema26
    signal = calculate_ema(macd, 9)

    return macd, signal


def calculate_score(symbol: str, df: pd.DataFrame):
    try:
        if df is None or df.empty:
            return None

        close = df["Close"]

        rsi_series = calculate_rsi(close)

        if rsi_series.dropna().empty:
            return None

        rsi = float(rsi_series.dropna().iloc[-1])

        macd, macd_signal = calculate_macd(close)

        if macd.dropna().empty:
            return None

        macd_value = float(macd.dropna().iloc[-1])
        macd_signal_value = float(macd_signal.dropna().iloc[-1])

        ema9 = float(calculate_ema(close, 9).iloc[-1])
        ema21 = float(calculate_ema(close, 21).iloc[-1])

        score = 0

        if rsi < 30:
            score += 25
        elif rsi < 50:
            score += 15
        elif rsi > 70:
            score -= 10

        if macd_value > macd_signal_value:
            score += 25
        else:
            score -= 10

        if ema9 > ema21:
            score += 25
            trend = "UPTREND"
        else:
            score -= 10
            trend = "DOWNTREND"

        if "Volume" in df.columns and len(df) > 20:
            volume_mean = df["Volume"].rolling(20).mean().iloc[-1]
            last_volume = df["Volume"].iloc[-1]

            if last_volume > volume_mean:
                score += 25

        return {
            "symbol": symbol,
            "score": max(score, 0),
            "trend": trend,
            "rsi": round(rsi, 2),
            "breakout": ema9 > ema21,
        }

    except Exception as exc:
        logger.warning("Score error %s: %s", symbol, exc)
        return None


def fetch_market_data():
    try:
        return get_market_data(SYMBOLS)
    except Exception as exc:
        logger.error("Market download error: %s", exc)
        return None


def _normalize_snapshot_ranking(snapshot_info: dict | None = None):
    snapshot_info = snapshot_info or get_snapshot_info()
    signal_count = int(snapshot_info.get("signals", 0) or 0)
    age_seconds = snapshot_info.get("age_seconds")

    if signal_count <= 0:
        return []

    if age_seconds is not None and age_seconds > SNAPSHOT_MAX_AGE:
        return []

    snapshot_rows = get_snapshot_signals()
    enriched_rows = ensure_final_decision_rows(
        ensure_institutional_priority_rows(
            ensure_institutional_conviction_rows(
                ensure_operational_rules_rows(
                    ensure_historical_confidence_rows(ensure_institutional_ranking_rows(snapshot_rows))
                )
            )
        )
    )
    has_ranking_contract = any(isinstance(row, dict) and "ranking_opportunity_score" in row for row in enriched_rows)
    ranking_rows = institutional_ranking_items(enriched_rows, limit=200)
    if not ranking_rows and not has_ranking_contract:
        ranking_rows = [row for row in enriched_rows if is_actionable_snapshot_row(row)]

    results = []

    for row in ranking_rows:
        if not isinstance(row, dict):
            continue

        if not is_actionable_snapshot_row(row):
            continue

        symbol = row.get("ticker") or row.get("symbol")

        if not symbol:
            continue

        try:
            ranking_score = float(row.get("ranking_opportunity_score", row.get("master_score", row.get("score", 0))) or 0)
        except Exception:
            ranking_score = 0.0
        try:
            display_score = float(row.get("master_score", row.get("score", 0)) or 0)
        except Exception:
            display_score = ranking_score
        display_contract = attach_master_score_display_contract(
            {
                "score": display_score,
                "master_score": row.get("master_score", display_score),
                "master_score_raw": row.get("master_score_raw"),
            }
        )

        results.append(
            {
                "ticker": symbol,
                "symbol": symbol,
                "score": display_score,
                "score_display": display_contract.get("master_score_display"),
                "master_score_display": display_contract.get("master_score_display"),
                "master_score_display_warning": display_contract.get("master_score_display_warning"),
                "master_score_raw": display_contract.get("master_score_raw"),
                "source_score": row.get("score"),
                "ranking_opportunity_score": row.get("ranking_opportunity_score", ranking_score),
                "ranking_classification": row.get("ranking_classification"),
                "ranking_reason": row.get("ranking_reason"),
                "ranking_summary": row.get("ranking_summary"),
                "ranking_eligible": row.get("ranking_eligible"),
                "ranking_excluded_reasons": row.get("ranking_excluded_reasons") or [],
                "master_score": display_contract.get("master_score"),
                "master_direction": row.get("master_direction"),
                "master_conviction": row.get("master_conviction"),
                "master_confidence": row.get("master_confidence"),
                "master_summary": row.get("master_summary"),
                "master_reasoning": row.get("master_reasoning") if isinstance(row.get("master_reasoning"), dict) else {},
                "master_risk": row.get("master_risk"),
                "master_status": row.get("master_status"),
                "master_visual_status": row.get("master_visual_status"),
                "master_visual_label": row.get("master_visual_label"),
                "opinion_change_conditions": row.get("opinion_change_conditions") or [],
                "strategic_panel": row.get("strategic_panel") if isinstance(row.get("strategic_panel"), dict) else {},
                "strategic_panel_summary": row.get("strategic_panel_summary") or "",
                "recommended_action": row.get("recommended_action"),
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
                "radar_prioritization_score": row.get("radar_prioritization_score"),
                "radar_priority_score": row.get("radar_priority_score"),
                "radar_priority": row.get("radar_priority"),
                "radar_level": row.get("radar_level"),
                "radar_reason": row.get("radar_reason"),
                "radar_summary": row.get("radar_summary"),
                "radar_no_trade_now": bool(row.get("radar_no_trade_now")),
                "radar_blocked_reasons": row.get("radar_blocked_reasons") or [],
                "trend": row.get("trend"),
                "rsi": row.get("rsi"),
                "breakout": bool(row.get("breakout", False)),
                "price": row.get("price"),
                "volume": row.get("volume"),
                "data_quality": coerce_data_quality(row),
                "data_quality_label": data_quality_label(coerce_data_quality(row)),
                "data_quality_score": data_quality_score(coerce_data_quality(row)),
                "market_data_updated_at": row.get("market_data_updated_at"),
                "last_updated": row.get("last_updated") or row.get("updated_at") or row.get("generated_at"),
                "quote_time": row.get("quote_time"),
                "provider_timestamp": row.get("provider_timestamp"),
                "updated_at": row.get("updated_at"),
                "generated_at": row.get("generated_at"),
                "snapshot_id": row.get("snapshot_id"),
                "is_stale": bool(row.get("stale") is True or row.get("is_stale") is True or coerce_data_quality(row) == "stale"),
                "fallback_used": bool(row.get("fallback_used")),
                "provider_error": row.get("provider_error"),
                "source": row.get("source") or "snapshot",
                "audit_status": row.get("audit_status"),
                "audit_score": row.get("audit_score"),
                "audit_confidence": row.get("audit_confidence"),
                "audit_summary": row.get("audit_summary"),
                "audit_blocks": row.get("audit_blocks") or [],
                "audit_warnings": row.get("audit_warnings") or [],
                "auditor_approved": row.get("auditor_approved"),
                "blocked_by_auditor": bool(row.get("blocked_by_auditor") is True),
            }
        )

    results.sort(key=lambda item: item.get("ranking_opportunity_score") or item["score"], reverse=True)
    return results


def _snapshot_signature(snapshot_info: dict) -> str:
    timestamp = (
        snapshot_info.get("timestamp")
        or snapshot_info.get("updated_at")
        or snapshot_info.get("generated_at")
        or snapshot_info.get("last_good_timestamp")
    )
    signals = int(snapshot_info.get("signals", 0) or 0)
    has_signals = bool(snapshot_info.get("has_signals"))
    is_empty = bool(snapshot_info.get("is_empty"))
    return f"{timestamp}|{signals}|{int(has_signals)}|{int(is_empty)}"


def _get_symbol_frame(data, symbol):
    if data is None:
        return None

    columns = getattr(data, "columns", None)

    if columns is None:
        return None

    if hasattr(columns, "levels"):
        available = set(columns.get_level_values(0))

        if symbol not in available:
            return None

        return data[symbol]

    if len(SYMBOLS) == 1 and symbol == SYMBOLS[0]:
        return data

    return None


def generate_ranking(force_refresh: bool = False, allow_external_fetch: bool = False):
    now = time.time()
    snapshot_info = get_snapshot_info()
    snapshot_signature = _snapshot_signature(snapshot_info)

    if (
        not force_refresh
        and _RANK_CACHE["data"]
        and _RANK_CACHE.get("snapshot_signature") == snapshot_signature
        and now - _RANK_CACHE["timestamp"] < CACHE_TTL
    ):
        return list(_RANK_CACHE["data"])

    snapshot_results = _normalize_snapshot_ranking(snapshot_info)

    if snapshot_results:
        _RANK_CACHE["data"] = list(snapshot_results)
        _RANK_CACHE["timestamp"] = now
        _RANK_CACHE["snapshot_signature"] = snapshot_signature
        return list(snapshot_results)

    if (
        not allow_external_fetch
        or not ALLOW_NETWORK_FALLBACK
        or current_provider_call_source() == "http"
    ):
        _RANK_CACHE["data"] = []
        _RANK_CACHE["timestamp"] = now
        _RANK_CACHE["snapshot_signature"] = snapshot_signature
        return []

    data = fetch_market_data()

    if data is None:
        _RANK_CACHE["data"] = []
        _RANK_CACHE["timestamp"] = now
        _RANK_CACHE["snapshot_signature"] = snapshot_signature
        return []

    results = []

    for symbol in SYMBOLS:
        try:
            frame = _get_symbol_frame(data, symbol)
            score = calculate_score(symbol, frame)

            if score:
                results.append(score)
        except Exception:
            continue

    results.sort(key=lambda row: row["score"], reverse=True)

    _RANK_CACHE["data"] = list(results)
    _RANK_CACHE["timestamp"] = now
    _RANK_CACHE["snapshot_signature"] = snapshot_signature

    return results


def get_ranking(force_refresh: bool = False, allow_external_fetch: bool = False):
    return generate_ranking(force_refresh=force_refresh, allow_external_fetch=allow_external_fetch)


def get_top_ranking(min_score: int = 50, limit: int = 10):
    ranking = get_ranking()
    return [row for row in ranking if row["score"] >= min_score][:limit]


def get_top_movers(limit: int = 10):
    return [row["symbol"] for row in get_ranking()[:limit]]


@router.get("")
def ranking_endpoint(current_user=Depends(require_active_plan)):
    del current_user
    return {"data": get_ranking()}


@router.get("/top")
def top_endpoint(min_score: int = 50, current_user=Depends(require_active_plan)):
    del current_user
    return {"data": get_top_ranking(min_score=min_score)}
