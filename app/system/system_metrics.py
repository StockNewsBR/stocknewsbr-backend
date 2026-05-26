# =====================================================
# STOCKNEWSBR SYSTEM METRICS
# =====================================================

import threading
import time
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar

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
_provider_call_source: ContextVar[str] = ContextVar("provider_call_source", default="unknown")

_HTTP_LATENCY_SAMPLE_LIMIT = 1024
_PROVIDER_FAILURE_LIMIT = 50

_http_endpoint_latency = {}
_cache_access = {}
_external_provider_calls = {}
_external_provider_symbol_calls = {}
_external_provider_failures = {}
_worker_stage_timings = {}
_signal_quality_coverage = {}


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


def _provider_metric_key(source: str, provider: str, operation: str, outcome: str) -> tuple[str, str, str, str]:
    return (
        str(source or "unknown"),
        str(provider or "unknown"),
        str(operation or "unknown"),
        str(outcome or "unknown"),
    )


def _provider_symbol_metric_key(source: str, provider: str, operation: str, outcome: str, symbol: str) -> tuple[str, str, str, str, str]:
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


def record_cache_lookup(cache_name: str, duration_seconds: float, size: int | None = None):
    duration = max(0.0, float(duration_seconds or 0.0))

    with _lock:
        entry = _cache_metric_entry(cache_name)
        lookup_count = int(entry.get("lookup_count", 0)) + 1
        total_lookup_seconds = float(entry.get("total_lookup_seconds", 0.0)) + duration
        entry["lookup_count"] = lookup_count
        entry["total_lookup_seconds"] = total_lookup_seconds
        entry["last_lookup_seconds"] = duration
        entry["max_lookup_seconds"] = max(float(entry.get("max_lookup_seconds", 0.0)), duration)
        entry["avg_lookup_seconds"] = total_lookup_seconds / max(1, lookup_count)
        if size is not None:
            entry["last_size"] = max(0, int(size or 0))


def record_http_endpoint_latency(route: str, method: str, status_code: int, duration_seconds: float):
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
    resolved_source = source or current_provider_call_source()
    outcome = "success" if success else "error"
    key = _provider_metric_key(resolved_source, provider, operation, outcome)
    duration = max(0.0, float(duration_seconds or 0.0))

    with _lock:
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

        symbol_key_value = str(symbol or "").upper().strip()
        if symbol_key_value:
            symbol_key = _provider_symbol_metric_key(resolved_source, provider, operation, outcome, symbol_key_value)
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
            symbol_entry["max_seconds"] = max(float(symbol_entry.get("max_seconds", 0.0)), duration)

        if not success and symbol:
            failure_key = str(symbol).upper().strip()
            if failure_key:
                failure = _external_provider_failures.setdefault(
                    failure_key,
                    {
                        "count": 0,
                        "provider": str(provider or "unknown"),
                        "operation": str(operation or "unknown"),
                        "source": str(resolved_source or "unknown"),
                        "last_error": "",
                        "last_seen": 0.0,
                    },
                )
                failure["count"] += 1
                failure["provider"] = str(provider or "unknown")
                failure["operation"] = str(operation or "unknown")
                failure["source"] = str(resolved_source or "unknown")
                failure["last_error"] = str(error or "")[:240]
                failure["last_seen"] = time.time()

                if len(_external_provider_failures) > _PROVIDER_FAILURE_LIMIT:
                    oldest = min(
                        _external_provider_failures,
                        key=lambda item: float(_external_provider_failures[item].get("last_seen", 0.0)),
                    )
                    _external_provider_failures.pop(oldest, None)


def record_worker_stage_duration(stage: str, duration_seconds: float, success: bool = True):
    duration = max(0.0, float(duration_seconds or 0.0))

    with _lock:
        entry = _worker_stage_entry(stage)
        entry["count"] += 1
        entry["total_seconds"] += duration
        entry["last_seconds"] = duration
        entry["max_seconds"] = max(float(entry.get("max_seconds", 0.0)), duration)
        if not success:
            entry["errors"] += 1


def _positive_number(value) -> bool:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return numeric > 0


def record_signal_quality_coverage(rows, source: str = "signal_cache"):
    safe_rows = [row for row in rows or [] if isinstance(row, dict)]
    total = len(safe_rows)
    price_count = sum(1 for row in safe_rows if _positive_number(row.get("price") or row.get("close") or row.get("last_price")))
    volume_count = sum(1 for row in safe_rows if _positive_number(row.get("volume") or row.get("last_volume")))
    priced_count = sum(1 for row in safe_rows if str(row.get("data_quality") or "").lower() == "priced")
    score_only_count = sum(1 for row in safe_rows if str(row.get("data_quality") or "").lower() == "score_only")
    decision_ready_count = sum(1 for row in safe_rows if row.get("decision_ready") is True)
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
                "last_lookup_seconds": round(float(entry.get("last_lookup_seconds", 0.0)), 6),
                "max_lookup_seconds": round(float(entry.get("max_lookup_seconds", 0.0)), 6),
                "avg_lookup_seconds": round(float(entry.get("avg_lookup_seconds", 0.0)), 6),
                "hit_ratio": round(
                    int(entry.get("hit", 0)) / max(1, int(entry.get("hit", 0)) + int(entry.get("miss", 0))),
                    4,
                ),
            }
            for name, entry in _cache_access.items()
        }

        provider_metrics = {}
        for (source, provider, operation, outcome), entry in _external_provider_calls.items():
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
                "avg_seconds": round(float(entry.get("total_seconds", 0.0)) / max(1, count), 6),
            }

        provider_symbol_metrics = {}
        for (source, provider, operation, outcome, symbol), entry in _external_provider_symbol_calls.items():
            count = int(entry.get("count", 0))
            provider_symbol_metrics[f"{source}:{provider}:{operation}:{outcome}:{symbol}"] = {
                "source": source,
                "provider": provider,
                "operation": operation,
                "outcome": outcome,
                "symbol": symbol,
                "count": count,
                "total_seconds": round(float(entry.get("total_seconds", 0.0)), 6),
                "last_seconds": round(float(entry.get("last_seconds", 0.0)), 6),
                "max_seconds": round(float(entry.get("max_seconds", 0.0)), 6),
                "avg_seconds": round(float(entry.get("total_seconds", 0.0)) / max(1, count), 6),
            }

        worker_metrics = {
            stage: {
                "count": int(entry.get("count", 0)),
                "errors": int(entry.get("errors", 0)),
                "total_seconds": round(float(entry.get("total_seconds", 0.0)), 6),
                "last_seconds": round(float(entry.get("last_seconds", 0.0)), 6),
                "max_seconds": round(float(entry.get("max_seconds", 0.0)), 6),
                "avg_seconds": round(float(entry.get("total_seconds", 0.0)) / max(1, int(entry.get("count", 0))), 6),
            }
            for stage, entry in _worker_stage_timings.items()
        }
        signal_quality = {
            source: dict(entry)
            for source, entry in _signal_quality_coverage.items()
        }

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
        "signal_quality_coverage": signal_quality,
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
        for quantile, value in (("0.50", item.get("p50")), ("0.95", item.get("p95")), ("0.99", item.get("p99"))):
            lines.append(
                'http_endpoint_latency_seconds{method="%s",route="%s",quantile="%s"} %s'
                % (_label_value(method), _label_value(route), quantile, float(value or 0.0))
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
        lines.append('cache_hit_total{cache="%s"} %s' % (_label_value(cache_name), int(item.get("hit", 0))))
        lines.append('cache_miss_total{cache="%s"} %s' % (_label_value(cache_name), int(item.get("miss", 0))))
        lines.append('cache_lookup_seconds{cache="%s",stat="last"} %s' % (_label_value(cache_name), float(item.get("last_lookup_seconds", 0.0))))
        lines.append('cache_lookup_seconds{cache="%s",stat="avg"} %s' % (_label_value(cache_name), float(item.get("avg_lookup_seconds", 0.0))))
        lines.append('cache_size{cache="%s"} %s' % (_label_value(cache_name), int(item.get("last_size", 0))))

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
        lines.append('worker_stage_seconds{stage="%s",stat="last"} %s' % (_label_value(stage), float(item.get("last_seconds", 0.0))))
        lines.append('worker_stage_seconds{stage="%s",stat="avg"} %s' % (_label_value(stage), float(item.get("avg_seconds", 0.0))))
        lines.append('worker_stage_errors_total{stage="%s"} %s' % (_label_value(stage), int(item.get("errors", 0))))

    for source, item in performance.get("signal_quality_coverage", {}).items():
        lines.append('signal_quality_rows_total{source="%s"} %s' % (_label_value(source), int(item.get("total", 0))))
        lines.append('signal_quality_coverage_ratio{source="%s",field="price"} %s' % (_label_value(source), float(item.get("price_coverage", 0.0))))
        lines.append('signal_quality_coverage_ratio{source="%s",field="volume"} %s' % (_label_value(source), float(item.get("volume_coverage", 0.0))))
        lines.append('signal_quality_coverage_ratio{source="%s",field="priced"} %s' % (_label_value(source), float(item.get("priced_coverage", 0.0))))
        lines.append('signal_quality_score_only_total{source="%s"} %s' % (_label_value(source), int(item.get("score_only", 0))))
        lines.append('signal_quality_conflict_total{source="%s"} %s' % (_label_value(source), int(item.get("conflict_detected", 0))))

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
        }
