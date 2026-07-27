from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from threading import RLock, Thread
from typing import Iterable

from app.market.market_data_loader import get_cached_chart_data, get_chart_data
from app.services.symbol_sanitizer import (
    is_symbol_on_cooldown,
    mark_symbol_cooldown,
    sanitize_market_symbol,
)
from app.system.system_metrics import provider_call_context, record_worker_stage_duration
from app.watchlists.watchlist_default import (
    WATCHLIST_B3,
    WATCHLIST_BDR,
    WATCHLIST_CRYPTO,
    WATCHLIST_US_GLOBAL,
)

logger = logging.getLogger("stocknewsbr.chart_warmup")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _project_runtime_path(env_name: str, default_relative: str) -> Path:
    configured = os.getenv(env_name)
    if configured:
        configured_path = Path(configured)
        return configured_path if configured_path.is_absolute() else _PROJECT_ROOT / configured_path
    return _PROJECT_ROOT / default_relative


REQUEST_PATH = _project_runtime_path("CHART_WARMUP_REQUEST_FILE", "runtime/cache/chart_warmup_requests.json")
DEFAULT_INTERVALS = tuple(
    item.strip().upper()
    for item in os.getenv("CHART_PREWARM_INTERVALS", "1D,1W,1M,3M,6M,YTD,1Y,ALL").split(",")
    if item.strip()
)
DEFAULT_CHART_COOLDOWN_SECONDS = max(120, int(os.getenv("CHART_WARMUP_COOLDOWN_SECONDS", "300")))
_REQUEST_LOCK = RLock()
_B3_MINI_FUTURE_RE = re.compile(r"^(WIN|WDO)[FGHJKMNQUVXZ]\d{2}$")
_pair_cooldowns: dict[str, float] = {}
_async_running: set[str] = set()


def _normalize_symbol(value: object) -> str:
    sanitized = sanitize_market_symbol(value)
    if not sanitized and value:
        mark_symbol_cooldown(value, "invalid_symbol")
    return sanitized or ""


def _normalize_interval(value: object) -> str:
    normalized = str(value or "1D").upper().strip()
    return "ALL" if normalized == "ALL" else normalized


def _pair_key(symbol: str, interval: str) -> str:
    ticker = _normalize_symbol(symbol)
    return f"{ticker}:{_normalize_interval(interval)}" if ticker else ""


def _is_on_cooldown(symbol: str, interval: str, now: float | None = None) -> bool:
    key = _pair_key(symbol, interval)
    if not key:
        return True
    if is_symbol_on_cooldown(symbol, now=now):
        return True
    current_time = now if now is not None else time.time()
    with _REQUEST_LOCK:
        cooldown_until = float(_pair_cooldowns.get(key) or 0.0)
    return cooldown_until > current_time


def _mark_cooldown(symbol: str, interval: str, seconds: int = DEFAULT_CHART_COOLDOWN_SECONDS) -> None:
    key = _pair_key(symbol, interval)
    if not key:
        return
    with _REQUEST_LOCK:
        _pair_cooldowns[key] = time.time() + max(60, int(seconds or DEFAULT_CHART_COOLDOWN_SECONDS))


def _is_blocked_chart_symbol(symbol: str) -> bool:
    compact = _normalize_symbol(symbol)
    if not compact:
        return True
    return bool(_B3_MINI_FUTURE_RE.match(compact))


def _read_requests() -> dict[str, dict]:
    try:
        if not REQUEST_PATH.exists():
            return {}
        payload = json.loads(REQUEST_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        requests = payload.get("requests", payload)
        return requests if isinstance(requests, dict) else {}
    except Exception:
        logger.exception("Failed to read chart warmup requests")
        return {}


def _write_requests(requests: dict[str, dict]) -> None:
    try:
        REQUEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_path = REQUEST_PATH.with_suffix(".tmp")
        temp_path.write_text(json.dumps({"requests": requests}, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(REQUEST_PATH)
    except Exception:
        logger.exception("Failed to write chart warmup requests")


def request_chart_warmup(symbol: str, interval: str = "1D") -> None:
    ticker = _normalize_symbol(symbol)
    chart_interval = _normalize_interval(interval)
    if not ticker or _is_blocked_chart_symbol(ticker):
        return

    key = f"{ticker}:{chart_interval}"
    now = time.time()
    with _REQUEST_LOCK:
        requests = _read_requests()
        current = dict(requests.get(key) or {})
        current.update(
            {
                "symbol": ticker,
                "interval": chart_interval,
                "requested_at": now,
                "count": int(current.get("count") or 0) + 1,
            }
        )
        requests[key] = current
        _write_requests(requests)


def request_on_demand_chart_warmup(symbol: str, intervals: Iterable[str] = ("1D", "3M")) -> bool:
    """Persist and immediately process cache misses without using the HTTP thread."""
    ticker = _normalize_symbol(symbol)
    pairs = [(ticker, _normalize_interval(interval)) for interval in intervals] if ticker else []
    pairs = [(item_symbol, interval) for item_symbol, interval in pairs if not _is_blocked_chart_symbol(item_symbol)]
    queued = False
    for item_symbol, interval in pairs:
        request_chart_warmup(item_symbol, interval)
        key = _pair_key(item_symbol, interval)
        with _REQUEST_LOCK:
            if key in _async_running or _is_on_cooldown(item_symbol, interval):
                continue
            _async_running.add(key)
            queued = True
        Thread(target=_warm_single_request, args=(item_symbol, interval, key), name=f"chart-warmup-{item_symbol}-{interval}", daemon=True).start()
    return queued


def _warm_single_request(symbol: str, interval: str, key: str) -> None:
    start = time.perf_counter()
    success = False
    try:
        # get_chart_data owns the interval-specific minimum. In particular, a
        # legacy 240-row crypto @5M cache is not enough for same-UTC-bucket
        # RVOL and must not short-circuit the longer background refresh.
        with provider_call_context("chart_request_warmup"):
            rows = get_chart_data(symbol, interval)
        success = bool(rows)
        if rows:
            _drop_warmed_requests([(symbol, interval)])
        else:
            _mark_cooldown(symbol, interval)
    except Exception:
        _mark_cooldown(symbol, interval)
        logger.exception("Async chart warmup failed | symbol=%s | interval=%s", symbol, interval)
    finally:
        with _REQUEST_LOCK:
            _async_running.discard(key)
        record_worker_stage_duration("chart_request_warmup", time.perf_counter() - start, success=success)


def _default_symbols(limit: int) -> list[str]:
    symbols: list[str] = []
    for group in (WATCHLIST_B3, WATCHLIST_BDR, WATCHLIST_US_GLOBAL, WATCHLIST_CRYPTO):
        for symbol in group:
            normalized = _normalize_symbol(symbol)
            if normalized and normalized not in symbols:
                symbols.append(normalized)
            if len(symbols) >= limit:
                return symbols
    return symbols


def _requested_pairs() -> list[tuple[str, str]]:
    with _REQUEST_LOCK:
        requests = _read_requests()
    rows = []
    for item in requests.values():
        symbol = _normalize_symbol(item.get("symbol"))
        interval = _normalize_interval(item.get("interval"))
        if not symbol or _is_blocked_chart_symbol(symbol):
            continue
        rows.append((float(item.get("requested_at") or 0.0), int(item.get("count") or 0), symbol, interval))
    rows.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [(symbol, interval) for _, _, symbol, interval in rows]


def _drop_warmed_requests(pairs: Iterable[tuple[str, str]]) -> None:
    pair_keys = {
        _pair_key(symbol, interval)
        for symbol, interval in pairs
        if _pair_key(symbol, interval)
    }
    if not pair_keys:
        return
    with _REQUEST_LOCK:
        requests = _read_requests()
        next_requests = {key: value for key, value in requests.items() if key not in pair_keys}
        if len(next_requests) != len(requests):
            _write_requests(next_requests)


def warm_charts_once(limit: int = 24, max_calls: int = 12, intervals: Iterable[str] | None = None) -> dict[str, int]:
    requested_pairs = _requested_pairs()
    configured_intervals = tuple(_normalize_interval(item) for item in (intervals or DEFAULT_INTERVALS)) or ("1D",)
    pairs: list[tuple[str, str]] = []

    for pair in requested_pairs:
        if pair not in pairs:
            pairs.append(pair)

    for symbol in _default_symbols(limit):
        for interval in configured_intervals:
            pair = (symbol, interval)
            if pair not in pairs:
                pairs.append(pair)

    warmed: list[tuple[str, str]] = []
    attempted = 0
    skipped = 0
    start = time.perf_counter()

    with provider_call_context("worker"):
        for symbol, interval in pairs:
            if attempted >= max_calls:
                break
            if _is_on_cooldown(symbol, interval):
                continue
            if get_cached_chart_data(symbol, interval):
                skipped += 1
                warmed.append((symbol, interval))
                continue
            attempted += 1
            try:
                rows = get_chart_data(symbol, interval)
                if rows:
                    warmed.append((symbol, interval))
                else:
                    _mark_cooldown(symbol, interval)
            except Exception as exc:
                _mark_cooldown(symbol, interval)
                logger.warning("Chart warmup failed | symbol=%s | interval=%s | error=%s", symbol, interval, exc)

    _drop_warmed_requests(warmed)
    record_worker_stage_duration("chart_warmup", time.perf_counter() - start, success=bool(warmed) or skipped > 0)
    return {"requested": len(requested_pairs), "attempted": attempted, "warmed": len(warmed), "skipped": skipped}
