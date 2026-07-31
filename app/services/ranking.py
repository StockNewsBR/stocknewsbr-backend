# =====================================================
# RANKING SERVICE
# Fast + Crash Safe
# =====================================================

from __future__ import annotations

import logging
import math
import os
import time

from fastapi import APIRouter, Depends
import pandas as pd

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
from app.engine.indicators.vector_indicator_engine import compute_latest_rsi
from app.services.score_display import attach_master_score_display_contract, normalize_master_score_display
from app.services.snapshot_contract import coerce_data_quality, data_quality_label, data_quality_score, is_actionable_snapshot_row, resolve_decision_envelope
from app.services.symbol_registry import canonical_symbol
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


def _numeric_score_or_none(value) -> float | None:
    if isinstance(value, bool):
        return None
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        missing = pd.isna(value)
        if bool(missing):
            return None
    except (TypeError, ValueError):
        pass
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _is_missing_score_value(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _first_numeric_score(*values, default: float = 0.0) -> float:
    for value in values:
        numeric = _numeric_score_or_none(value)
        if numeric is not None:
            return numeric
    return default


def _ranking_sort_score(row: dict) -> float:
    ranking_score = _numeric_score_or_none(row.get("ranking_opportunity_score"))
    if ranking_score is not None:
        return _canonical_score(ranking_score, _ranking_scale_hint(row))
    score = row.get("score")
    return _canonical_score(score, _score_scale_hint(row) or _scale_hint_for_value(score), default=0.0)


def _ranking_symbol_key(row: dict) -> str:
    return canonical_symbol(row.get("canonical_symbol") or row.get("ticker") or row.get("symbol")) or str(
        row.get("ticker") or row.get("symbol") or ""
    ).upper()


def _ranking_order_key(row: dict) -> tuple[float, str]:
    return (-_ranking_sort_score(row), _ranking_symbol_key(row))


def _ranking_dedupe_key(row: dict) -> tuple[float, int, str]:
    normalized_source = 1 if str(row.get("master_score_source_scale") or "") == "0_10" else 0
    return (_ranking_sort_score(row), normalized_source, _ranking_symbol_key(row))


def _scale_hint_for_value(value, explicit_scale: str | None = None) -> str:
    if explicit_scale in {"0_10", "0_100"}:
        return explicit_scale
    numeric = _numeric_score_or_none(value)
    if numeric is not None and numeric > 10.0:
        return "0_100"
    return "0_10"


def _source_scale_hint(row: dict) -> str | None:
    for key in ("master_score_source_scale", "master_score_scale", "source_scale"):
        value = str(row.get(key) or "").strip()
        if value in {"0_10", "0_100"}:
            return value
    return None


def _score_scale_hint(row: dict) -> str | None:
    for key in ("score_source_scale", "source_scale"):
        value = str(row.get(key) or "").strip()
        if value in {"0_10", "0_100"}:
            return value
    return None


def _ranking_scale_hint(row: dict) -> str | None:
    for key in ("ranking_opportunity_source_scale", "ranking_score_source_scale"):
        value = str(row.get(key) or "").strip()
        if value in {"0_10", "0_100"}:
            return value
    return None


def _canonical_score(value, explicit_scale: str | None = None, default: float = 0.0) -> float:
    numeric = _numeric_score_or_none(value)
    if numeric is None:
        return default
    display, warning = normalize_master_score_display(numeric, source_scale=_scale_hint_for_value(numeric, explicit_scale))
    return default if warning and warning != "master_score_normalized_from_raw_100" else display


def _score_field_scale(row: dict, value) -> str:
    scale_hint = _score_scale_hint(row)
    return _scale_hint_for_value(value, scale_hint)


def _valid_score_for_scale(numeric: float, scale: str) -> bool:
    if scale == "0_100":
        return 0.0 <= numeric <= 100.0
    if scale == "0_10":
        return 0.0 <= numeric <= 10.0
    return False


def _score_candidate(
    row: dict,
    *keys: str,
    default: float | None = 0.0,
    default_scale: str = "0_10",
) -> tuple[float | None, str, bool]:
    invalid_seen = False
    for key in keys:
        value = row.get(key)
        numeric = _numeric_score_or_none(value)
        if numeric is None:
            if key in row and not _is_missing_score_value(value):
                invalid_seen = True
            continue
        if key == "master_score_raw":
            scale = "0_100"
            if _valid_score_for_scale(numeric, scale):
                return numeric, scale, invalid_seen
            invalid_seen = True
            continue
        if key == "ranking_opportunity_score":
            raw_numeric = _numeric_score_or_none(row.get("master_score_raw"))
            scale = _ranking_scale_hint(row)
            if scale is None and raw_numeric is not None and raw_numeric > 10.0 and numeric == raw_numeric:
                scale = "0_100"
            scale = scale or _scale_hint_for_value(value)
            if _valid_score_for_scale(numeric, scale):
                return numeric, scale, invalid_seen
            invalid_seen = True
            continue
        scale_hint = _score_scale_hint(row) if key == "score" else _source_scale_hint(row)
        scale = _score_field_scale(row, value) if key == "score" else _scale_hint_for_value(value, scale_hint)
        if _valid_score_for_scale(numeric, scale):
            return numeric, scale, invalid_seen
        invalid_seen = True
    return default, default_scale, invalid_seen


def _master_score_source(row: dict) -> tuple[float | None, str]:
    raw_score = row.get("master_score_raw")
    raw_numeric = _numeric_score_or_none(raw_score)
    explicit_scale = _source_scale_hint(row)
    if raw_numeric is not None and _valid_score_for_scale(raw_numeric, "0_100"):
        return raw_numeric, "0_100"

    for key in ("master_score", "score"):
        value = row.get(key)
        numeric = _numeric_score_or_none(value)
        if numeric is not None:
            scale = _score_field_scale(row, value) if key == "score" else _scale_hint_for_value(value, explicit_scale)
            if _valid_score_for_scale(numeric, scale):
                return numeric, scale
    return None, "0_10"


def _normalize_calculated_ranking_item(item: dict) -> dict | None:
    raw_score = item.get("score")
    score_scale = _score_scale_hint(item)
    if score_scale is None and item.get("master_score") == raw_score:
        score_scale = _source_scale_hint(item)
    score_scale = score_scale or _scale_hint_for_value(raw_score)
    display_contract = attach_master_score_display_contract(
        {
            "score": raw_score,
            "master_score": raw_score,
            "master_score_raw": raw_score if score_scale == "0_100" else None,
            "master_score_source_scale": score_scale,
        }
    )
    if display_contract.get("master_score_display_warning") == "master_score_display_invalid":
        return None
    ranking_source = item.get("ranking_opportunity_score")
    ranking_contract = display_contract
    if _numeric_score_or_none(ranking_source) is not None:
        ranking_scale = _ranking_scale_hint(item) or _scale_hint_for_value(ranking_source)
        ranking_contract = attach_master_score_display_contract(
            {
                "score": ranking_source,
                "master_score": ranking_source,
                "master_score_raw": ranking_source if ranking_scale == "0_100" else None,
                "master_score_source_scale": ranking_scale,
            }
        )
        if ranking_contract.get("master_score_display_warning") == "master_score_display_invalid":
            return None
    return {
        **item,
        "score": display_contract.get("master_score", 0.0),
        "score_source_scale": "0_10",
        "score_display": display_contract.get("master_score_display"),
        "master_score": display_contract.get("master_score"),
        "master_score_display": display_contract.get("master_score_display"),
        "master_score_display_warning": display_contract.get("master_score_display_warning"),
        "master_score_raw": display_contract.get("master_score_raw"),
        "master_score_source_scale": display_contract.get("master_score_source_scale"),
        "ranking_opportunity_score": ranking_contract.get("master_score", 0.0),
        "ranking_opportunity_source_scale": "0_10",
        "ranking_score_source_scale": "0_10",
    }


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

        # Single source of truth: the canonical Wilder/RMA RSI (TradingView
        # parity). ranking used to carry its own Cutler copy that drifted up to
        # ~15 RSI points from the engine on the same candles.
        rsi = compute_latest_rsi(close)

        if rsi is None:
            return None

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

        symbol = canonical_symbol(row.get("canonical_symbol") or row.get("ticker") or row.get("symbol"))

        if not symbol:
            continue

        raw_ranking_score, ranking_source_scale, ranking_invalid = _score_candidate(
            row,
            "ranking_opportunity_score",
            default=None,
        )
        if raw_ranking_score is None and not ranking_invalid:
            raw_ranking_score, ranking_source_scale, ranking_invalid = _score_candidate(
                row,
                "master_score_raw",
                "master_score",
                "score",
                default=None,
            )
        if ranking_invalid:
            continue
        if raw_ranking_score is None:
            raw_ranking_score = 0.0
        ranking_score = _canonical_score(raw_ranking_score, ranking_source_scale)
        raw_display_score, display_source_scale, display_invalid = _score_candidate(
            row,
            "master_score_raw",
            "master_score",
            "score",
            "ranking_opportunity_score",
            default=raw_ranking_score,
            default_scale=ranking_source_scale,
        )
        if raw_display_score is None:
            raw_display_score = raw_ranking_score
        if display_invalid:
            continue
        display_score = _canonical_score(raw_display_score, display_source_scale, default=ranking_score)
        master_score_input, master_score_source_scale = _master_score_source(row)
        has_master_score_source = master_score_input is not None
        if not has_master_score_source:
            master_score_input = display_score
            master_score_source_scale = "0_10"
        display_contract = attach_master_score_display_contract(
            {
                "score": display_score,
                "master_score": master_score_input,
                "master_score_raw": master_score_input if master_score_source_scale == "0_100" else None,
                "master_score_source_scale": master_score_source_scale,
            }
        )
        if display_contract.get("master_score_display_warning") == "master_score_display_invalid":
            continue
        normalized_score = display_contract.get("master_score", display_score)
        decision_envelope = resolve_decision_envelope(row)

        results.append(
            {
                "ticker": symbol,
                "symbol": symbol,
                "score": normalized_score,
                "score_display": display_contract.get("master_score_display"),
                "master_score_display": display_contract.get("master_score_display"),
                "master_score_display_warning": display_contract.get("master_score_display_warning"),
                "master_score_raw": display_contract.get("master_score_raw"),
                "master_score_source_scale": display_contract.get("master_score_source_scale"),
                "source_score": row.get("score"),
                "decision_status": decision_envelope.get("decision_status"),
                "decision_envelope": decision_envelope,
                "ranking_opportunity_score": ranking_score,
                "score_source_scale": "0_10",
                "ranking_opportunity_source_scale": "0_10",
                "ranking_score_source_scale": "0_10",
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

    deduped: dict[str, dict] = {}
    for item in results:
        symbol = canonical_symbol(item.get("ticker") or item.get("symbol"))
        if not symbol:
            continue
        item["ticker"] = symbol
        item["symbol"] = symbol
        item["canonical_symbol"] = symbol
        current = deduped.get(symbol)
        if current is None or _ranking_dedupe_key(item) > _ranking_dedupe_key(current):
            deduped[symbol] = item

    output = list(deduped.values())
    output.sort(key=_ranking_order_key)
    return output


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
                normalized_score = _normalize_calculated_ranking_item(score)
                if normalized_score:
                    results.append(normalized_score)
        except Exception as exc:
            logger.warning("Ranking fallback error %s: %s", symbol, exc)
            continue

    results.sort(key=_ranking_order_key)

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
