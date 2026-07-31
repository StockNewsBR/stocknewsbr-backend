# =====================================================
# STOCKNEWSBR SYSTEM METRICS
# =====================================================

import math
import threading
import time
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar

from app.services.score_display import resolve_master_score_display_value

# =====================================================
# ENGINE METRICS
# =====================================================

engine_cycles = 0
last_scan_time = 0.0
last_signals_generated = 0
assets_scanned = 0

engine_start_time = time.time()

# =====================================================
# CACHE METRICS
# =====================================================

cache_last_update = 0.0

# =====================================================
# WORKER METRICS
# =====================================================

workers = 0
http_requests = 0
http_errors = 0
ws_connections = 0
chat_messages = 0
reports_created = 0
uploads_completed = 0
push_sends = 0

_lock = threading.RLock()
_provider_call_source: ContextVar[str] = ContextVar(
    "provider_call_source", default="unknown"
)

_HTTP_LATENCY_SAMPLE_LIMIT = 1024
_PROVIDER_FAILURE_LIMIT = 50
_EXTERNAL_PROVIDER_CALLS_LIMIT = 1000
_EXTERNAL_PROVIDER_SYMBOL_CALLS_LIMIT = 2000

_http_endpoint_latency = {}
_cache_access = {}
_external_provider_calls = {}
_external_provider_symbol_calls = {}
_external_provider_failures = {}
_worker_stage_timings = {}
_worker_runtime_metrics = {
    "worker_generation_success": 0,
    "worker_generation_failure": 0,
    "snapshot_write_success": 0,
    "snapshot_write_failure": 0,
    "updated_at": 0.0,
}
_signal_quality_coverage = {}
_institutional_auditor_metrics = {
    "approved": 0,
    "caution": 0,
    "blocked": 0,
    "average_audit_score": 0.0,
    "updated_at": 0.0,
}
_master_score_metrics = {
    "signals": 0,
    "approved": 0,
    "caution": 0,
    "blocked": 0,
    "bullish": 0,
    "bearish": 0,
    "neutral": 0,
    "average_master_score": 0.0,
    "updated_at": 0.0,
}
_institutional_radar_metrics = {
    "generated": 0,
    "promoted": 0,
    "discarded": 0,
    "blocked": 0,
    "updated_at": 0.0,
}
_institutional_ranking_metrics = {
    "eligible": 0,
    "excluded": 0,
    "promoted": 0,
    "top_ranking": 0,
    "updated_at": 0.0,
}
_historical_confidence_metrics = {
    "signals": 0,
    "average_confidence_score": 0.0,
    "average_sample_size": 0.0,
    "signals_without_sample": 0,
    "aggregate_win_rate": 0.0,
    "by_ticker": {},
    "updated_at": 0.0,
}
_operational_rules_metrics = {
    "ready": 0,
    "caution": 0,
    "blocked": 0,
    "top_blocks": {},
    "top_warnings": {},
    "updated_at": 0.0,
}
_institutional_conviction_metrics = {
    "signals": 0,
    "average_conviction": 0.0,
    "high_conviction": 0,
    "low_conviction": 0,
    "conflicts_detected": 0,
    "updated_at": 0.0,
}
_institutional_priority_metrics = {
    "critical": 0,
    "high": 0,
    "medium": 0,
    "low": 0,
    "updated_at": 0.0,
}
_final_decision_metrics = {
    "confirmed": 0,
    "forming": 0,
    "observe": 0,
    "wait": 0,
    "no_trade": 0,
    "updated_at": 0.0,
}
_telegram_alert_metrics = {
    "sent": 0,
    "blocked": 0,
    "discarded": 0,
    "deduplicated": 0,
    "cooldown": 0,
    "errors": 0,
    "critical": 0,
    "high": 0,
    "medium": 0,
    "updated_at": 0.0,
}
_signal_outcome_metrics = {
    "total_signals": 0,
    "executable_signals": 0,
    "blocked_signals": 0,
    "skipped_signals": 0,
    "insufficient_data": 0,
    "evaluated_executable_signals": 0,
    "winner_signals": 0,
    "loser_signals": 0,
    "neutral_signals": 0,
    "win_rate": 0.0,
    "average_mfe_pct": 0.0,
    "average_mae_pct": 0.0,
    "average_payoff": 0.0,
    "simulated_drawdown_pct": 0.0,
    "block_rate": 0.0,
    "false_positive_rate": 0.0,
    "false_negative_rate": 0.0,
    "insufficient_data_rate": 0.0,
    "blocked_would_have_won": 0,
    "blocked_correctly": 0,
    "released_failed": 0,
    "released_won": 0,
    "updated_at": 0.0,
}
_performance_intelligence_metrics = {
    "status": "IDLE",
    "sample_size": 0,
    "assets": 0,
    "regimes": 0,
    "score_buckets": 0,
    "blocked_correctly": 0,
    "blocked_would_have_won": 0,
    "released_failed": 0,
    "released_won": 0,
    "auditor_efficiency": None,
    "recommendations": 0,
    "updated_at": 0.0,
}
_explainability_metrics = {
    "status": "IDLE",
    "explanations": 0,
    "average_decision_explainability_score": 0.0,
    "high_explainability": 0,
    "low_explainability": 0,
    "missing_change_conditions": 0,
    "updated_at": 0.0,
}
_institutional_consistency_metrics = {
    "signals_checked": 0,
    "issues": 0,
    "direction_conflicts": 0,
    "priority_no_trade": 0,
    "approved_operational_blocked": 0,
    "documented_operational_blocks": 0,
    "missing_contracts": 0,
    "contract_complete": 0,
    "contract_coverage_pct": 0.0,
    "go_live_inconsistencies": 0,
    "promotion_violations": 0,
    "metric_divergences": 0,
    "consistency_score": 0.0,
    "updated_at": 0.0,
}


def _quantile(sorted_values, quantile: float) -> float:
    if not sorted_values:
        return 0.0

    index = int(round((len(sorted_values) - 1) * quantile))
    index = max(0, min(index, len(sorted_values) - 1))
    return round(float(sorted_values[index]), 6)


def _route_metric_key(method: str, route: str) -> tuple[str, str]:
    return (str(method or "GET").upper(), str(route or "unknown"))


def _cache_metric_entry(cache_name: str):
    return _cache_access.setdefault(
        str(cache_name or "unknown"),
        {
            "hit": 0,
            "miss": 0,
            "sources": {},
        },
    )


def _provider_metric_key(
    source: str, provider: str, operation: str, outcome: str
) -> tuple[str, str, str, str]:
    return (
        str(source or "unknown"),
        str(provider or "unknown"),
        str(operation or "unknown"),
        str(outcome or "unknown"),
    )


def _sanitize_metric_label(
    val: str, default: str = "unknown", max_len: int = 48
) -> str:
    cleaned = str(val or "").strip()
    if not cleaned:
        return default
    if len(cleaned) > max_len or any(
        c in cleaned
        for c in (
            "?",
            "=",
            "&",
            "/",
            "\\",
            "<",
            ">",
            '"',
            "'",
            "{",
            "}",
            "\n",
            "\r",
            " ",
        )
    ):
        return "other"
    return cleaned


def _sanitize_symbol_label(val: str) -> str:
    cleaned = str(val or "").strip().upper()
    if not cleaned:
        return ""
    if len(cleaned) > 16 or any(
        c in cleaned
        for c in (
            "?",
            "=",
            "&",
            "/",
            "\\",
            "<",
            ">",
            '"',
            "'",
            "{",
            "}",
            "\n",
            "\r",
            " ",
        )
    ):
        return "OTHER"
    return cleaned


def _provider_symbol_metric_key(
    source: str, provider: str, operation: str, outcome: str, symbol: str
) -> tuple[str, str, str, str, str]:
    return (
        str(source or "unknown"),
        str(provider or "unknown"),
        str(operation or "unknown"),
        str(outcome or "unknown"),
        str(symbol or "unknown").upper().strip(),
    )


def _worker_stage_entry(stage: str):
    return _worker_stage_timings.setdefault(
        str(stage or "unknown"),
        {
            "count": 0,
            "errors": 0,
            "total_seconds": 0.0,
            "last_seconds": 0.0,
            "max_seconds": 0.0,
        },
    )


# =====================================================
# ENGINE FUNCTIONS
# =====================================================


def increment_engine_cycles():
    global engine_cycles

    with _lock:
        engine_cycles += 1


def set_scan_time(scan_time):
    global last_scan_time

    with _lock:
        last_scan_time = float(scan_time or 0.0)


def set_signals_generated(count):
    global last_signals_generated

    with _lock:
        last_signals_generated = int(count or 0)


def set_assets_scanned(count):
    global assets_scanned

    with _lock:
        assets_scanned = int(count or 0)


# =====================================================
# CACHE FUNCTIONS
# =====================================================


def update_cache_timestamp(timestamp=None):
    global cache_last_update

    with _lock:
        cache_last_update = float(timestamp or time.time())


def get_cache_age():
    with _lock:
        last_update = cache_last_update

    if last_update == 0:
        return None

    return int(time.time() - last_update)


def record_cache_access(cache_name: str, hit: bool, source: str | None = None):
    with _lock:
        entry = _cache_metric_entry(cache_name)
        bucket = "hit" if hit else "miss"
        entry[bucket] += 1
        if source:
            sources = entry.setdefault("sources", {})
            key = str(source)
            sources[key] = int(sources.get(key, 0)) + 1


def record_cache_lookup(
    cache_name: str, duration_seconds: float, size: int | None = None
):
    duration = max(0.0, float(duration_seconds or 0.0))

    with _lock:
        entry = _cache_metric_entry(cache_name)
        lookup_count = int(entry.get("lookup_count", 0)) + 1
        total_lookup_seconds = float(entry.get("total_lookup_seconds", 0.0)) + duration
        entry["lookup_count"] = lookup_count
        entry["total_lookup_seconds"] = total_lookup_seconds
        entry["last_lookup_seconds"] = duration
        entry["max_lookup_seconds"] = max(
            float(entry.get("max_lookup_seconds", 0.0)), duration
        )
        entry["avg_lookup_seconds"] = total_lookup_seconds / max(1, lookup_count)
        if size is not None:
            entry["last_size"] = max(0, int(size or 0))


def record_http_endpoint_latency(
    route: str, method: str, status_code: int, duration_seconds: float
):
    key = _route_metric_key(method, route)
    status = int(status_code or 0)
    duration = max(0.0, float(duration_seconds or 0.0))

    with _lock:
        entry = _http_endpoint_latency.setdefault(
            key,
            {
                "samples": deque(maxlen=_HTTP_LATENCY_SAMPLE_LIMIT),
                "count": 0,
                "errors": 0,
                "last_status": status,
                "last_seconds": 0.0,
                "max_seconds": 0.0,
            },
        )
        entry["samples"].append(duration)
        entry["count"] += 1
        entry["last_status"] = status
        entry["last_seconds"] = duration
        entry["max_seconds"] = max(float(entry.get("max_seconds", 0.0)), duration)
        if status >= 500:
            entry["errors"] += 1


def current_provider_call_source() -> str:
    return _provider_call_source.get()


@contextmanager
def provider_call_context(source: str):
    token = _provider_call_source.set(str(source or "unknown"))
    try:
        yield
    finally:
        _provider_call_source.reset(token)


def record_external_provider_call(
    provider: str,
    operation: str,
    duration_seconds: float | None = None,
    success: bool = True,
    source: str | None = None,
    symbol: str | None = None,
    error: str | None = None,
):
    resolved_source = _sanitize_metric_label(
        source or current_provider_call_source(), default="unknown", max_len=32
    )
    resolved_provider = _sanitize_metric_label(provider, default="unknown", max_len=32)
    resolved_operation = _sanitize_metric_label(
        operation, default="unknown", max_len=48
    )
    outcome = "success" if success else "error"
    key = _provider_metric_key(
        resolved_source, resolved_provider, resolved_operation, outcome
    )
    duration = max(0.0, float(duration_seconds or 0.0))

    with _lock:
        if (
            key not in _external_provider_calls
            and len(_external_provider_calls) >= _EXTERNAL_PROVIDER_CALLS_LIMIT
        ):
            key = _provider_metric_key(resolved_source, "other", "other", outcome)
            if (
                key not in _external_provider_calls
                and len(_external_provider_calls) >= _EXTERNAL_PROVIDER_CALLS_LIMIT
            ):
                # Evict oldest entry if at strict capacity
                oldest_key = next(iter(_external_provider_calls))
                _external_provider_calls.pop(oldest_key, None)

        entry = _external_provider_calls.setdefault(
            key,
            {
                "count": 0,
                "total_seconds": 0.0,
                "last_seconds": 0.0,
                "max_seconds": 0.0,
            },
        )
        entry["count"] += 1
        entry["total_seconds"] += duration
        entry["last_seconds"] = duration
        entry["max_seconds"] = max(float(entry.get("max_seconds", 0.0)), duration)

        symbol_key_value = _sanitize_symbol_label(symbol or "")
        if symbol_key_value:
            symbol_key = _provider_symbol_metric_key(
                resolved_source,
                resolved_provider,
                resolved_operation,
                outcome,
                symbol_key_value,
            )
            if (
                symbol_key not in _external_provider_symbol_calls
                and len(_external_provider_symbol_calls)
                >= _EXTERNAL_PROVIDER_SYMBOL_CALLS_LIMIT
            ):
                symbol_key = _provider_symbol_metric_key(
                    resolved_source,
                    resolved_provider,
                    resolved_operation,
                    outcome,
                    "OTHER",
                )
                if (
                    symbol_key not in _external_provider_symbol_calls
                    and len(_external_provider_symbol_calls)
                    >= _EXTERNAL_PROVIDER_SYMBOL_CALLS_LIMIT
                ):
                    oldest_sym_key = next(iter(_external_provider_symbol_calls))
                    _external_provider_symbol_calls.pop(oldest_sym_key, None)

            symbol_entry = _external_provider_symbol_calls.setdefault(
                symbol_key,
                {
                    "count": 0,
                    "total_seconds": 0.0,
                    "last_seconds": 0.0,
                    "max_seconds": 0.0,
                },
            )
            symbol_entry["count"] += 1
            symbol_entry["total_seconds"] += duration
            symbol_entry["last_seconds"] = duration
            symbol_entry["max_seconds"] = max(
                float(symbol_entry.get("max_seconds", 0.0)), duration
            )

        if not success and symbol_key_value:
            failure_key = symbol_key_value
            if failure_key:
                failure = _external_provider_failures.setdefault(
                    failure_key,
                    {
                        "count": 0,
                        "provider": resolved_provider,
                        "operation": resolved_operation,
                        "source": resolved_source,
                        "last_error": "",
                        "last_seen": 0.0,
                    },
                )
                failure["count"] += 1
                failure["provider"] = resolved_provider
                failure["operation"] = resolved_operation
                failure["source"] = resolved_source
                failure["last_error"] = str(error or "")[:240]
                failure["last_seen"] = time.time()

                if len(_external_provider_failures) > _PROVIDER_FAILURE_LIMIT:
                    oldest = min(
                        _external_provider_failures,
                        key=lambda item: float(
                            _external_provider_failures[item].get("last_seen", 0.0)
                        ),
                    )
                    _external_provider_failures.pop(oldest, None)


def record_worker_stage_duration(
    stage: str, duration_seconds: float, success: bool = True
):
    duration = max(0.0, float(duration_seconds or 0.0))

    with _lock:
        entry = _worker_stage_entry(stage)
        entry["count"] += 1
        entry["total_seconds"] += duration
        entry["last_seconds"] = duration
        entry["max_seconds"] = max(float(entry.get("max_seconds", 0.0)), duration)
        if not success:
            entry["errors"] += 1


def record_worker_generation_metric(success: bool):
    key = "worker_generation_success" if success else "worker_generation_failure"
    with _lock:
        _worker_runtime_metrics[key] += 1
        _worker_runtime_metrics["updated_at"] = time.time()


def record_snapshot_write_metric(success: bool):
    key = "snapshot_write_success" if success else "snapshot_write_failure"
    with _lock:
        _worker_runtime_metrics[key] += 1
        _worker_runtime_metrics["updated_at"] = time.time()


def get_worker_runtime_metrics_snapshot():
    with _lock:
        return dict(_worker_runtime_metrics)


def _positive_number(value) -> bool:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return numeric > 0


def record_signal_quality_coverage(rows, source: str = "signal_cache"):
    safe_rows = [row for row in rows or [] if isinstance(row, dict)]
    total = len(safe_rows)
    price_count = sum(
        1
        for row in safe_rows
        if _positive_number(
            row.get("price") or row.get("close") or row.get("last_price")
        )
    )
    volume_count = sum(
        1
        for row in safe_rows
        if _positive_number(row.get("volume") or row.get("last_volume"))
    )
    priced_count = sum(
        1 for row in safe_rows if str(row.get("data_quality") or "").lower() == "priced"
    )
    score_only_count = sum(
        1
        for row in safe_rows
        if str(row.get("data_quality") or "").lower() == "score_only"
    )
    decision_ready_count = sum(
        1 for row in safe_rows if row.get("decision_ready") is True
    )
    conflict_count = sum(1 for row in safe_rows if row.get("conflict_detected") is True)

    with _lock:
        _signal_quality_coverage[str(source or "unknown")] = {
            "total": total,
            "with_price": price_count,
            "with_volume": volume_count,
            "priced": priced_count,
            "score_only": score_only_count,
            "decision_ready": decision_ready_count,
            "conflict_detected": conflict_count,
            "price_coverage": round(price_count / max(1, total), 4),
            "volume_coverage": round(volume_count / max(1, total), 4),
            "priced_coverage": round(priced_count / max(1, total), 4),
            "updated_at": time.time(),
        }


def record_institutional_auditor_metrics(metrics: dict | None):
    safe = metrics if isinstance(metrics, dict) else {}
    with _lock:
        _institutional_auditor_metrics.update(
            {
                "approved": int(safe.get("approved", 0) or 0),
                "caution": int(safe.get("caution", 0) or 0),
                "blocked": int(safe.get("blocked", 0) or 0),
                "average_audit_score": round(
                    float(safe.get("avg_audit_score", 0.0) or 0.0), 2
                ),
                "updated_at": time.time(),
            }
        )


def get_institutional_auditor_metrics_snapshot():
    with _lock:
        return dict(_institutional_auditor_metrics)


def record_master_score_metrics(rows_or_metrics):
    if isinstance(rows_or_metrics, dict):
        safe = rows_or_metrics
        try:
            average_master_score = float(safe.get("average_master_score", 0.0) or 0.0)
        except (TypeError, ValueError):
            average_master_score = 0.0
        if not math.isfinite(average_master_score):
            average_master_score = 0.0
        with _lock:
            _master_score_metrics.update(
                {
                    "signals": int(safe.get("signals", 0) or 0),
                    "approved": int(safe.get("approved", 0) or 0),
                    "caution": int(safe.get("caution", 0) or 0),
                    "blocked": int(safe.get("blocked", 0) or 0),
                    "bullish": int(safe.get("bullish", 0) or 0),
                    "bearish": int(safe.get("bearish", 0) or 0),
                    "neutral": int(safe.get("neutral", 0) or 0),
                    "average_master_score": round(average_master_score or 0.0, 2),
                    "updated_at": time.time(),
                }
            )
        return

    rows = [row for row in rows_or_metrics or [] if isinstance(row, dict)]
    scores = []
    status_counts = {"approved": 0, "caution": 0, "blocked": 0}
    direction_counts = {"bullish": 0, "bearish": 0, "neutral": 0}
    for row in rows:
        try:
            display_score, warning, _ = resolve_master_score_display_value(row)
            if display_score is not None and warning in (
                None,
                "master_score_normalized_from_raw_100",
            ):
                scores.append(display_score)
        except (TypeError, ValueError):
            pass
        status = str(row.get("master_status") or "").strip().lower()
        if status in status_counts:
            status_counts[status] += 1
        direction = str(row.get("master_direction") or "").strip().lower()
        if direction in direction_counts:
            direction_counts[direction] += 1

    with _lock:
        _master_score_metrics.update(
            {
                "signals": len(rows),
                **status_counts,
                **direction_counts,
                "average_master_score": round(sum(scores) / len(scores), 2)
                if scores
                else 0.0,
                "updated_at": time.time(),
            }
        )


def get_master_score_metrics_snapshot():
    with _lock:
        return dict(_master_score_metrics)


def record_institutional_radar_metrics(metrics: dict | None):
    safe = metrics if isinstance(metrics, dict) else {}
    with _lock:
        _institutional_radar_metrics.update(
            {
                "generated": int(safe.get("generated", 0) or 0),
                "promoted": int(safe.get("promoted", 0) or 0),
                "discarded": int(safe.get("discarded", 0) or 0),
                "blocked": int(safe.get("blocked", 0) or 0),
                "updated_at": time.time(),
            }
        )


def get_institutional_radar_metrics_snapshot():
    with _lock:
        return dict(_institutional_radar_metrics)


def record_institutional_ranking_metrics(metrics: dict | None):
    safe = metrics if isinstance(metrics, dict) else {}
    with _lock:
        _institutional_ranking_metrics.update(
            {
                "eligible": int(safe.get("eligible", 0) or 0),
                "excluded": int(safe.get("excluded", 0) or 0),
                "promoted": int(safe.get("promoted", 0) or 0),
                "top_ranking": int(safe.get("top_ranking", 0) or 0),
                "updated_at": time.time(),
            }
        )


def get_institutional_ranking_metrics_snapshot():
    with _lock:
        return dict(_institutional_ranking_metrics)


def record_historical_confidence_metrics(metrics: dict | None):
    safe = metrics if isinstance(metrics, dict) else {}
    with _lock:
        _historical_confidence_metrics.update(
            {
                "signals": int(safe.get("signals", 0) or 0),
                "average_confidence_score": round(
                    float(safe.get("average_confidence_score", 0.0) or 0.0), 2
                ),
                "average_sample_size": round(
                    float(safe.get("average_sample_size", 0.0) or 0.0), 2
                ),
                "signals_without_sample": int(
                    safe.get("signals_without_sample", 0) or 0
                ),
                "aggregate_win_rate": round(
                    float(safe.get("aggregate_win_rate", 0.0) or 0.0), 2
                ),
                "by_ticker": dict(
                    safe.get("by_ticker", {})
                    if isinstance(safe.get("by_ticker"), dict)
                    else {}
                ),
                "updated_at": time.time(),
            }
        )


def get_historical_confidence_metrics_snapshot():
    with _lock:
        return dict(_historical_confidence_metrics)


def record_operational_rules_metrics(metrics: dict | None):
    safe = metrics if isinstance(metrics, dict) else {}
    with _lock:
        _operational_rules_metrics.update(
            {
                "ready": int(safe.get("ready", 0) or 0),
                "caution": int(safe.get("caution", 0) or 0),
                "blocked": int(safe.get("blocked", 0) or 0),
                "top_blocks": dict(
                    safe.get("top_blocks", {})
                    if isinstance(safe.get("top_blocks"), dict)
                    else {}
                ),
                "top_warnings": dict(
                    safe.get("top_warnings", {})
                    if isinstance(safe.get("top_warnings"), dict)
                    else {}
                ),
                "updated_at": time.time(),
            }
        )


def get_operational_rules_metrics_snapshot():
    with _lock:
        return dict(_operational_rules_metrics)


def record_institutional_conviction_metrics(metrics: dict | None):
    safe = metrics if isinstance(metrics, dict) else {}
    with _lock:
        _institutional_conviction_metrics.update(
            {
                "signals": int(safe.get("signals", 0) or 0),
                "average_conviction": round(
                    float(safe.get("average_conviction", 0.0) or 0.0), 2
                ),
                "high_conviction": int(safe.get("high_conviction", 0) or 0),
                "low_conviction": int(safe.get("low_conviction", 0) or 0),
                "conflicts_detected": int(safe.get("conflicts_detected", 0) or 0),
                "updated_at": time.time(),
            }
        )


def get_institutional_conviction_metrics_snapshot():
    with _lock:
        return dict(_institutional_conviction_metrics)


def record_institutional_priority_metrics(metrics: dict | None):
    safe = metrics if isinstance(metrics, dict) else {}
    with _lock:
        _institutional_priority_metrics.update(
            {
                "critical": int(safe.get("critical", 0) or 0),
                "high": int(safe.get("high", 0) or 0),
                "medium": int(safe.get("medium", 0) or 0),
                "low": int(safe.get("low", 0) or 0),
                "updated_at": time.time(),
            }
        )


def get_institutional_priority_metrics_snapshot():
    with _lock:
        return dict(_institutional_priority_metrics)


def record_final_decision_metrics(metrics: dict | None):
    safe = metrics if isinstance(metrics, dict) else {}
    with _lock:
        _final_decision_metrics.update(
            {
                "confirmed": int(safe.get("confirmed", 0) or 0),
                "forming": int(safe.get("forming", 0) or 0),
                "observe": int(safe.get("observe", 0) or 0),
                "wait": int(safe.get("wait", 0) or 0),
                "no_trade": int(safe.get("no_trade", 0) or 0),
                "updated_at": time.time(),
            }
        )


def get_final_decision_metrics_snapshot():
    with _lock:
        return dict(_final_decision_metrics)


def record_telegram_alert_metric(event: str, alert_level: str | None = None):
    metric = str(event or "").strip().lower()
    level = str(alert_level or "").strip().lower()
    with _lock:
        if metric in _telegram_alert_metrics:
            _telegram_alert_metrics[metric] = (
                int(_telegram_alert_metrics.get(metric, 0) or 0) + 1
            )
        if metric == "sent" and level in {"critical", "high", "medium"}:
            _telegram_alert_metrics[level] = (
                int(_telegram_alert_metrics.get(level, 0) or 0) + 1
            )
        _telegram_alert_metrics["updated_at"] = time.time()


def get_telegram_alert_metrics_snapshot():
    with _lock:
        return dict(_telegram_alert_metrics)


def record_signal_outcome_metrics(metrics: dict | None):
    safe = metrics if isinstance(metrics, dict) else {}
    with _lock:
        _signal_outcome_metrics.update(
            {
                "total_signals": int(safe.get("total_signals", 0) or 0),
                "executable_signals": int(safe.get("executable_signals", 0) or 0),
                "blocked_signals": int(safe.get("blocked_signals", 0) or 0),
                "skipped_signals": int(safe.get("skipped_signals", 0) or 0),
                "insufficient_data": int(safe.get("insufficient_data", 0) or 0),
                "evaluated_executable_signals": int(
                    safe.get("evaluated_executable_signals", 0) or 0
                ),
                "winner_signals": int(safe.get("winner_signals", 0) or 0),
                "loser_signals": int(safe.get("loser_signals", 0) or 0),
                "neutral_signals": int(safe.get("neutral_signals", 0) or 0),
                "win_rate": round(float(safe.get("win_rate", 0.0) or 0.0), 2),
                "average_mfe_pct": round(
                    float(safe.get("average_mfe_pct", 0.0) or 0.0), 4
                ),
                "average_mae_pct": round(
                    float(safe.get("average_mae_pct", 0.0) or 0.0), 4
                ),
                "average_payoff": round(
                    float(safe.get("average_payoff", 0.0) or 0.0), 4
                ),
                "simulated_drawdown_pct": round(
                    float(safe.get("simulated_drawdown_pct", 0.0) or 0.0), 4
                ),
                "block_rate": round(float(safe.get("block_rate", 0.0) or 0.0), 2),
                "false_positive_rate": round(
                    float(safe.get("false_positive_rate", 0.0) or 0.0), 2
                ),
                "false_negative_rate": round(
                    float(safe.get("false_negative_rate", 0.0) or 0.0), 2
                ),
                "insufficient_data_rate": round(
                    float(safe.get("insufficient_data_rate", 0.0) or 0.0), 2
                ),
                "blocked_would_have_won": int(
                    safe.get("blocked_would_have_won", 0) or 0
                ),
                "blocked_correctly": int(safe.get("blocked_correctly", 0) or 0),
                "released_failed": int(safe.get("released_failed", 0) or 0),
                "released_won": int(safe.get("released_won", 0) or 0),
                "updated_at": time.time(),
            }
        )


def get_signal_outcome_metrics_snapshot():
    with _lock:
        return dict(_signal_outcome_metrics)


def record_performance_intelligence_metrics(metrics: dict | None):
    safe = metrics if isinstance(metrics, dict) else {}
    auditor = (
        safe.get("auditor_efficiency")
        if isinstance(safe.get("auditor_efficiency"), dict)
        else {}
    )
    with _lock:
        _performance_intelligence_metrics.update(
            {
                "status": str(safe.get("status") or "IDLE"),
                "sample_size": int(safe.get("sample_size", 0) or 0),
                "assets": len(
                    safe.get("by_asset", {})
                    if isinstance(safe.get("by_asset"), dict)
                    else {}
                ),
                "regimes": len(
                    safe.get("by_regime", {})
                    if isinstance(safe.get("by_regime"), dict)
                    else {}
                ),
                "score_buckets": len(
                    safe.get("by_score_bucket", {})
                    if isinstance(safe.get("by_score_bucket"), dict)
                    else {}
                ),
                "blocked_correctly": int(safe.get("blocked_correctly", 0) or 0),
                "blocked_would_have_won": int(
                    safe.get("blocked_would_have_won", 0) or 0
                ),
                "released_failed": int(safe.get("released_failed", 0) or 0),
                "released_won": int(safe.get("released_won", 0) or 0),
                "auditor_efficiency": auditor.get("institutional_auditor_efficiency"),
                "recommendations": len(
                    safe.get("recommendations", [])
                    if isinstance(safe.get("recommendations"), list)
                    else []
                ),
                "updated_at": time.time(),
            }
        )


def get_performance_intelligence_metrics_snapshot():
    with _lock:
        return dict(_performance_intelligence_metrics)


def record_explainability_metrics(metrics: dict | None):
    safe = metrics if isinstance(metrics, dict) else {}
    with _lock:
        _explainability_metrics.update(
            {
                "status": str(safe.get("status") or "IDLE"),
                "explanations": int(safe.get("explanations", 0) or 0),
                "average_decision_explainability_score": round(
                    float(
                        safe.get("average_decision_explainability_score", 0.0) or 0.0
                    ),
                    2,
                ),
                "high_explainability": int(safe.get("high_explainability", 0) or 0),
                "low_explainability": int(safe.get("low_explainability", 0) or 0),
                "missing_change_conditions": int(
                    safe.get("missing_change_conditions", 0) or 0
                ),
                "updated_at": time.time(),
            }
        )


def get_explainability_metrics_snapshot():
    with _lock:
        return dict(_explainability_metrics)


def record_institutional_consistency_metrics(metrics: dict | None):
    safe = metrics if isinstance(metrics, dict) else {}
    with _lock:
        _institutional_consistency_metrics.update(
            {
                "signals_checked": int(safe.get("signals_checked", 0) or 0),
                "issues": int(safe.get("issues", 0) or 0),
                "direction_conflicts": int(safe.get("direction_conflicts", 0) or 0),
                "priority_no_trade": int(safe.get("priority_no_trade", 0) or 0),
                "approved_operational_blocked": int(
                    safe.get("approved_operational_blocked", 0) or 0
                ),
                "documented_operational_blocks": int(
                    safe.get("documented_operational_blocks", 0) or 0
                ),
                "missing_contracts": int(safe.get("missing_contracts", 0) or 0),
                "contract_complete": int(safe.get("contract_complete", 0) or 0),
                "contract_coverage_pct": round(
                    float(safe.get("contract_coverage_pct", 0.0) or 0.0), 2
                ),
                "go_live_inconsistencies": int(
                    safe.get("go_live_inconsistencies", 0) or 0
                ),
                "promotion_violations": int(safe.get("promotion_violations", 0) or 0),
                "metric_divergences": int(safe.get("metric_divergences", 0) or 0),
                "consistency_score": round(
                    float(safe.get("consistency_score", 0.0) or 0.0), 2
                ),
                "updated_at": time.time(),
            }
        )


def get_institutional_consistency_metrics_snapshot():
    with _lock:
        return dict(_institutional_consistency_metrics)


def _institutional_metrics_snapshot_locked():
    return {
        "institutional_auditor": dict(_institutional_auditor_metrics),
        "master_score": dict(_master_score_metrics),
        "historical_confidence": dict(_historical_confidence_metrics),
        "operational_rules": dict(_operational_rules_metrics),
        "institutional_conviction": dict(_institutional_conviction_metrics),
        "institutional_priority": dict(_institutional_priority_metrics),
        "institutional_radar": dict(_institutional_radar_metrics),
        "institutional_ranking": dict(_institutional_ranking_metrics),
        "final_decision": dict(_final_decision_metrics),
        "telegram_alerts": dict(_telegram_alert_metrics),
        "signal_outcomes": dict(_signal_outcome_metrics),
        "institutional_consistency": dict(_institutional_consistency_metrics),
    }


def get_performance_metrics_snapshot():
    with _lock:
        http_metrics = {}
        for (method, route), entry in _http_endpoint_latency.items():
            samples = sorted(float(value) for value in entry.get("samples", []))
            http_metrics[f"{method} {route}"] = {
                "count": int(entry.get("count", 0)),
                "errors": int(entry.get("errors", 0)),
                "last_status": int(entry.get("last_status", 0)),
                "last_seconds": round(float(entry.get("last_seconds", 0.0)), 6),
                "max_seconds": round(float(entry.get("max_seconds", 0.0)), 6),
                "p50": _quantile(samples, 0.50),
                "p95": _quantile(samples, 0.95),
                "p99": _quantile(samples, 0.99),
                "sample_count": len(samples),
            }

        cache_metrics = {
            name: {
                "hit": int(entry.get("hit", 0)),
                "miss": int(entry.get("miss", 0)),
                "sources": dict(entry.get("sources", {})),
                "lookup_count": int(entry.get("lookup_count", 0)),
                "last_size": int(entry.get("last_size", 0)),
                "last_lookup_seconds": round(
                    float(entry.get("last_lookup_seconds", 0.0)), 6
                ),
                "max_lookup_seconds": round(
                    float(entry.get("max_lookup_seconds", 0.0)), 6
                ),
                "avg_lookup_seconds": round(
                    float(entry.get("avg_lookup_seconds", 0.0)), 6
                ),
                "hit_ratio": round(
                    int(entry.get("hit", 0))
                    / max(1, int(entry.get("hit", 0)) + int(entry.get("miss", 0))),
                    4,
                ),
            }
            for name, entry in _cache_access.items()
        }

        provider_metrics = {}
        for (
            source,
            provider,
            operation,
            outcome,
        ), entry in _external_provider_calls.items():
            count = int(entry.get("count", 0))
            provider_metrics[f"{source}:{provider}:{operation}:{outcome}"] = {
                "source": source,
                "provider": provider,
                "operation": operation,
                "outcome": outcome,
                "count": count,
                "total_seconds": round(float(entry.get("total_seconds", 0.0)), 6),
                "last_seconds": round(float(entry.get("last_seconds", 0.0)), 6),
                "max_seconds": round(float(entry.get("max_seconds", 0.0)), 6),
                "avg_seconds": round(
                    float(entry.get("total_seconds", 0.0)) / max(1, count), 6
                ),
            }

        provider_symbol_metrics = {}
        for (
            source,
            provider,
            operation,
            outcome,
            symbol,
        ), entry in _external_provider_symbol_calls.items():
            count = int(entry.get("count", 0))
            provider_symbol_metrics[
                f"{source}:{provider}:{operation}:{outcome}:{symbol}"
            ] = {
                "source": source,
                "provider": provider,
                "operation": operation,
                "outcome": outcome,
                "symbol": symbol,
                "count": count,
                "total_seconds": round(float(entry.get("total_seconds", 0.0)), 6),
                "last_seconds": round(float(entry.get("last_seconds", 0.0)), 6),
                "max_seconds": round(float(entry.get("max_seconds", 0.0)), 6),
                "avg_seconds": round(
                    float(entry.get("total_seconds", 0.0)) / max(1, count), 6
                ),
            }

        worker_metrics = {
            stage: {
                "count": int(entry.get("count", 0)),
                "errors": int(entry.get("errors", 0)),
                "total_seconds": round(float(entry.get("total_seconds", 0.0)), 6),
                "last_seconds": round(float(entry.get("last_seconds", 0.0)), 6),
                "max_seconds": round(float(entry.get("max_seconds", 0.0)), 6),
                "avg_seconds": round(
                    float(entry.get("total_seconds", 0.0))
                    / max(1, int(entry.get("count", 0))),
                    6,
                ),
            }
            for stage, entry in _worker_stage_timings.items()
        }
        signal_quality = {
            source: dict(entry) for source, entry in _signal_quality_coverage.items()
        }
        institutional_radar = dict(_institutional_radar_metrics)
        institutional_ranking = dict(_institutional_ranking_metrics)
        institutional_auditor = dict(_institutional_auditor_metrics)
        master_score = dict(_master_score_metrics)
        historical_confidence = dict(_historical_confidence_metrics)
        operational_rules = dict(_operational_rules_metrics)
        institutional_conviction = dict(_institutional_conviction_metrics)
        institutional_priority = dict(_institutional_priority_metrics)
        final_decision = dict(_final_decision_metrics)
        telegram_alerts = dict(_telegram_alert_metrics)
        signal_outcomes = dict(_signal_outcome_metrics)
        performance_intelligence = dict(_performance_intelligence_metrics)
        explainability = dict(_explainability_metrics)
        institutional_consistency = dict(_institutional_consistency_metrics)
        institutional_metrics = _institutional_metrics_snapshot_locked()
        worker_runtime = dict(_worker_runtime_metrics)

        repeated_failures = sorted(
            (
                {
                    "symbol": symbol,
                    "count": int(entry.get("count", 0)),
                    "provider": entry.get("provider"),
                    "operation": entry.get("operation"),
                    "source": entry.get("source"),
                    "last_error": entry.get("last_error"),
                    "last_seen": entry.get("last_seen"),
                }
                for symbol, entry in _external_provider_failures.items()
            ),
            key=lambda item: item["count"],
            reverse=True,
        )

    return {
        "http_endpoint_latency_seconds": http_metrics,
        "cache": cache_metrics,
        "external_provider_call_total": provider_metrics,
        "external_provider_symbol_call_total": provider_symbol_metrics,
        "worker_stage_seconds": worker_metrics,
        "worker_runtime": worker_runtime,
        "signal_quality_coverage": signal_quality,
        "institutional_auditor": institutional_auditor,
        "master_score": master_score,
        "institutional_radar": institutional_radar,
        "institutional_ranking": institutional_ranking,
        "historical_confidence": historical_confidence,
        "operational_rules": operational_rules,
        "institutional_conviction": institutional_conviction,
        "institutional_priority": institutional_priority,
        "final_decision": final_decision,
        "telegram_alerts": telegram_alerts,
        "signal_outcomes": signal_outcomes,
        "performance_intelligence": performance_intelligence,
        "explainability": explainability,
        "institutional_consistency": institutional_consistency,
        "institutional_metrics": institutional_metrics,
        "provider_symbol_failures": repeated_failures,
    }


def _label_value(value) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def format_prometheus_metrics() -> str:
    base = get_metrics_snapshot()
    performance = get_performance_metrics_snapshot()
    lines = [
        "# HELP stocknewsbr_http_requests_total Total HTTP requests observed by the API process.",
        "# TYPE stocknewsbr_http_requests_total counter",
        f"stocknewsbr_http_requests_total {int(base.get('http_requests', 0))}",
        "# HELP stocknewsbr_http_errors_total Total HTTP 5xx errors observed by the API process.",
        "# TYPE stocknewsbr_http_errors_total counter",
        f"stocknewsbr_http_errors_total {int(base.get('http_errors', 0))}",
        "# HELP stocknewsbr_engine_cycles_total Engine cycles observed by the API process.",
        "# TYPE stocknewsbr_engine_cycles_total counter",
        f"stocknewsbr_engine_cycles_total {int(base.get('engine_cycles', 0))}",
        "# HELP stocknewsbr_workers Current active worker count.",
        "# TYPE stocknewsbr_workers gauge",
        f"stocknewsbr_workers {int(base.get('workers', 0))}",
    ]

    for route_key, item in performance.get("http_endpoint_latency_seconds", {}).items():
        method, _, route = route_key.partition(" ")
        for quantile, value in (
            ("0.50", item.get("p50")),
            ("0.95", item.get("p95")),
            ("0.99", item.get("p99")),
        ):
            lines.append(
                'http_endpoint_latency_seconds{method="%s",route="%s",quantile="%s"} %s'
                % (
                    _label_value(method),
                    _label_value(route),
                    quantile,
                    float(value or 0.0),
                )
            )
        lines.append(
            'http_endpoint_requests_total{method="%s",route="%s"} %s'
            % (_label_value(method), _label_value(route), int(item.get("count", 0)))
        )
        lines.append(
            'http_endpoint_errors_total{method="%s",route="%s"} %s'
            % (_label_value(method), _label_value(route), int(item.get("errors", 0)))
        )

    for cache_name, item in performance.get("cache", {}).items():
        lines.append(
            'cache_hit_total{cache="%s"} %s'
            % (_label_value(cache_name), int(item.get("hit", 0)))
        )
        lines.append(
            'cache_miss_total{cache="%s"} %s'
            % (_label_value(cache_name), int(item.get("miss", 0)))
        )
        lines.append(
            'cache_lookup_seconds{cache="%s",stat="last"} %s'
            % (_label_value(cache_name), float(item.get("last_lookup_seconds", 0.0)))
        )
        lines.append(
            'cache_lookup_seconds{cache="%s",stat="avg"} %s'
            % (_label_value(cache_name), float(item.get("avg_lookup_seconds", 0.0)))
        )
        lines.append(
            'cache_size{cache="%s"} %s'
            % (_label_value(cache_name), int(item.get("last_size", 0)))
        )

    for item in performance.get("external_provider_call_total", {}).values():
        lines.append(
            'external_provider_call_total{source="%s",provider="%s",operation="%s",outcome="%s"} %s'
            % (
                _label_value(item.get("source")),
                _label_value(item.get("provider")),
                _label_value(item.get("operation")),
                _label_value(item.get("outcome")),
                int(item.get("count", 0)),
            )
        )

    for item in performance.get("external_provider_symbol_call_total", {}).values():
        lines.append(
            'external_provider_symbol_call_total{source="%s",provider="%s",operation="%s",outcome="%s",symbol="%s"} %s'
            % (
                _label_value(item.get("source")),
                _label_value(item.get("provider")),
                _label_value(item.get("operation")),
                _label_value(item.get("outcome")),
                _label_value(item.get("symbol")),
                int(item.get("count", 0)),
            )
        )

    for stage, item in performance.get("worker_stage_seconds", {}).items():
        lines.append(
            'worker_stage_seconds{stage="%s",stat="last"} %s'
            % (_label_value(stage), float(item.get("last_seconds", 0.0)))
        )
        lines.append(
            'worker_stage_seconds{stage="%s",stat="avg"} %s'
            % (_label_value(stage), float(item.get("avg_seconds", 0.0)))
        )
        lines.append(
            'worker_stage_errors_total{stage="%s"} %s'
            % (_label_value(stage), int(item.get("errors", 0)))
        )

    worker_runtime = performance.get("worker_runtime", {})
    for field in (
        "worker_generation_success",
        "worker_generation_failure",
        "snapshot_write_success",
        "snapshot_write_failure",
    ):
        lines.append(
            "worker_runtime_%s_total %s"
            % (_label_value(field), int(worker_runtime.get(field, 0)))
        )

    for source, item in performance.get("signal_quality_coverage", {}).items():
        lines.append(
            'signal_quality_rows_total{source="%s"} %s'
            % (_label_value(source), int(item.get("total", 0)))
        )
        lines.append(
            'signal_quality_coverage_ratio{source="%s",field="price"} %s'
            % (_label_value(source), float(item.get("price_coverage", 0.0)))
        )
        lines.append(
            'signal_quality_coverage_ratio{source="%s",field="volume"} %s'
            % (_label_value(source), float(item.get("volume_coverage", 0.0)))
        )
        lines.append(
            'signal_quality_coverage_ratio{source="%s",field="priced"} %s'
            % (_label_value(source), float(item.get("priced_coverage", 0.0)))
        )
        lines.append(
            'signal_quality_score_only_total{source="%s"} %s'
            % (_label_value(source), int(item.get("score_only", 0)))
        )
        lines.append(
            'signal_quality_conflict_total{source="%s"} %s'
            % (_label_value(source), int(item.get("conflict_detected", 0)))
        )

    auditor_metrics = performance.get("institutional_auditor", {})
    for field in ("approved", "caution", "blocked"):
        lines.append(
            'institutional_auditor_total{status="%s"} %s'
            % (_label_value(field), int(auditor_metrics.get(field, 0)))
        )
    lines.append(
        "institutional_auditor_average_score %s"
        % float(auditor_metrics.get("average_audit_score", 0.0))
    )

    master_metrics = performance.get("master_score", {})
    for field in ("approved", "caution", "blocked"):
        lines.append(
            'master_score_total{status="%s"} %s'
            % (_label_value(field), int(master_metrics.get(field, 0)))
        )
    for field in ("bullish", "bearish", "neutral"):
        lines.append(
            'master_score_direction_total{direction="%s"} %s'
            % (_label_value(field), int(master_metrics.get(field, 0)))
        )
    lines.append(
        "master_score_average %s"
        % float(master_metrics.get("average_master_score", 0.0))
    )

    radar_metrics = performance.get("institutional_radar", {})
    for field in ("generated", "promoted", "discarded", "blocked"):
        lines.append(
            'institutional_radar_signals_total{state="%s"} %s'
            % (_label_value(field), int(radar_metrics.get(field, 0)))
        )

    ranking_metrics = performance.get("institutional_ranking", {})
    for field in ("eligible", "excluded", "promoted", "top_ranking"):
        lines.append(
            'institutional_ranking_opportunities_total{state="%s"} %s'
            % (_label_value(field), int(ranking_metrics.get(field, 0)))
        )

    historical_metrics = performance.get("historical_confidence", {})
    lines.append(
        "historical_confidence_average_score %s"
        % float(historical_metrics.get("average_confidence_score", 0.0))
    )
    lines.append(
        "historical_confidence_average_sample_size %s"
        % float(historical_metrics.get("average_sample_size", 0.0))
    )
    lines.append(
        "historical_confidence_without_sample_total %s"
        % int(historical_metrics.get("signals_without_sample", 0))
    )
    lines.append(
        "historical_confidence_aggregate_win_rate %s"
        % float(historical_metrics.get("aggregate_win_rate", 0.0))
    )

    operational_metrics = performance.get("operational_rules", {})
    for field in ("ready", "caution", "blocked"):
        lines.append(
            'operational_rules_signals_total{status="%s"} %s'
            % (_label_value(field), int(operational_metrics.get(field, 0)))
        )
    for reason, count in operational_metrics.get("top_blocks", {}).items():
        lines.append(
            'operational_rules_reasons_total{kind="block",reason="%s"} %s'
            % (_label_value(reason), int(count or 0))
        )
    for reason, count in operational_metrics.get("top_warnings", {}).items():
        lines.append(
            'operational_rules_reasons_total{kind="warning",reason="%s"} %s'
            % (_label_value(reason), int(count or 0))
        )

    conviction_metrics = performance.get("institutional_conviction", {})
    lines.append(
        "institutional_conviction_average_score %s"
        % float(conviction_metrics.get("average_conviction", 0.0))
    )
    lines.append(
        "institutional_conviction_high_total %s"
        % int(conviction_metrics.get("high_conviction", 0))
    )
    lines.append(
        "institutional_conviction_low_total %s"
        % int(conviction_metrics.get("low_conviction", 0))
    )
    lines.append(
        "institutional_conviction_conflicts_total %s"
        % int(conviction_metrics.get("conflicts_detected", 0))
    )

    priority_metrics = performance.get("institutional_priority", {})
    for field in ("critical", "high", "medium", "low"):
        lines.append(
            'institutional_priority_total{level="%s"} %s'
            % (_label_value(field), int(priority_metrics.get(field, 0)))
        )

    final_metrics = performance.get("final_decision", {})
    for field in ("confirmed", "forming", "observe", "wait", "no_trade"):
        lines.append(
            'final_decision_total{decision="%s"} %s'
            % (_label_value(field), int(final_metrics.get(field, 0)))
        )

    telegram_metrics = performance.get("telegram_alerts", {})
    for field in ("sent", "blocked", "discarded", "deduplicated", "cooldown", "errors"):
        lines.append(
            'telegram_alert_events_total{event="%s"} %s'
            % (_label_value(field), int(telegram_metrics.get(field, 0)))
        )
    for field in ("critical", "high", "medium"):
        lines.append(
            'telegram_alerts_total{level="%s"} %s'
            % (_label_value(field), int(telegram_metrics.get(field, 0)))
        )

    consistency_metrics = performance.get("institutional_consistency", {})
    for field in (
        "issues",
        "direction_conflicts",
        "priority_no_trade",
        "approved_operational_blocked",
        "documented_operational_blocks",
        "missing_contracts",
        "go_live_inconsistencies",
        "promotion_violations",
        "metric_divergences",
    ):
        lines.append(
            'institutional_consistency_total{type="%s"} %s'
            % (_label_value(field), int(consistency_metrics.get(field, 0)))
        )
    lines.append(
        "institutional_consistency_score %s"
        % float(consistency_metrics.get("consistency_score", 0.0))
    )
    lines.append(
        "institutional_contract_coverage_pct %s"
        % float(consistency_metrics.get("contract_coverage_pct", 0.0))
    )

    for item in performance.get("provider_symbol_failures", []):
        lines.append(
            'provider_symbol_failure_total{symbol="%s",provider="%s",operation="%s",source="%s"} %s'
            % (
                _label_value(item.get("symbol")),
                _label_value(item.get("provider")),
                _label_value(item.get("operation")),
                _label_value(item.get("source")),
                int(item.get("count", 0)),
            )
        )

    return "\n".join(lines) + "\n"


# =====================================================
# WORKER FUNCTIONS
# =====================================================


def set_workers(count):
    global workers

    with _lock:
        workers = max(0, int(count or 0))


def increment_http_requests():
    global http_requests

    with _lock:
        http_requests += 1


def increment_http_errors():
    global http_errors

    with _lock:
        http_errors += 1


def increment_ws_connections():
    global ws_connections

    with _lock:
        ws_connections += 1


def decrement_ws_connections():
    global ws_connections

    with _lock:
        ws_connections = max(0, ws_connections - 1)


def increment_chat_messages():
    global chat_messages

    with _lock:
        chat_messages += 1


def increment_reports():
    global reports_created

    with _lock:
        reports_created += 1


def increment_uploads():
    global uploads_completed

    with _lock:
        uploads_completed += 1


def increment_push_sends():
    global push_sends

    with _lock:
        push_sends += 1


# =====================================================
# ENGINE UPTIME
# =====================================================


def get_engine_uptime():
    return int(time.time() - engine_start_time)


# =====================================================
# PERFORMANCE CALCULATIONS
# =====================================================


def get_signals_per_second():
    with _lock:
        scan_time = last_scan_time
        signal_count = last_signals_generated

    if scan_time == 0:
        return 0

    return round(signal_count / scan_time, 2)


def get_scan_frequency():
    uptime = get_engine_uptime()

    if uptime == 0:
        return 0

    with _lock:
        cycle_count = engine_cycles

    return round(cycle_count / uptime, 4)


def get_metrics_snapshot():
    with _lock:
        institutional_metrics = _institutional_metrics_snapshot_locked()
        return {
            "engine_cycles": engine_cycles,
            "scan_time": round(last_scan_time, 4) if last_scan_time else 0,
            "signals_generated": last_signals_generated,
            "assets_scanned": assets_scanned,
            "workers": workers,
            "cache_age": get_cache_age(),
            "http_requests": http_requests,
            "http_errors": http_errors,
            "ws_connections": ws_connections,
            "chat_messages": chat_messages,
            "reports_created": reports_created,
            "uploads_completed": uploads_completed,
            "push_sends": push_sends,
            "institutional_auditor": institutional_metrics["institutional_auditor"],
            "master_score": institutional_metrics["master_score"],
            "historical_confidence": institutional_metrics["historical_confidence"],
            "operational_rules": institutional_metrics["operational_rules"],
            "institutional_conviction": institutional_metrics[
                "institutional_conviction"
            ],
            "institutional_priority": institutional_metrics["institutional_priority"],
            "institutional_radar": institutional_metrics["institutional_radar"],
            "institutional_ranking": institutional_metrics["institutional_ranking"],
            "final_decision": institutional_metrics["final_decision"],
            "telegram_alerts": institutional_metrics["telegram_alerts"],
            "signal_outcomes": institutional_metrics["signal_outcomes"],
            "institutional_consistency": institutional_metrics[
                "institutional_consistency"
            ],
            "worker_runtime": dict(_worker_runtime_metrics),
            "institutional_metrics": institutional_metrics,
        }
