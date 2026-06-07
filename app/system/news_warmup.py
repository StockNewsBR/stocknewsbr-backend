from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from threading import RLock, Thread
from typing import Iterable

from app.services.news_service import get_cached_symbol_news, get_symbol_news
from app.system.system_metrics import provider_call_context, record_worker_stage_duration

logger = logging.getLogger("stocknewsbr.news_warmup")

DEFAULT_NEWS_WARMUP_INTERVAL_SECONDS = max(120, int(os.getenv("NEWS_WARMUP_INTERVAL_SECONDS", "300")))
DEFAULT_NEWS_WARMUP_LIMIT = max(8, int(os.getenv("NEWS_WARMUP_LIMIT", "24")))
DEFAULT_NEWS_WARMUP_MAX_CALLS = max(4, int(os.getenv("NEWS_WARMUP_MAX_CALLS", "12")))
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _project_runtime_path(env_name: str, default_relative: str) -> Path:
    configured = os.getenv(env_name)
    if configured:
        configured_path = Path(configured)
        return configured_path if configured_path.is_absolute() else _PROJECT_ROOT / configured_path
    return _PROJECT_ROOT / default_relative


REQUEST_PATH = _project_runtime_path("NEWS_WARMUP_REQUEST_FILE", "runtime/cache/news_warmup_requests.json")

_lock = RLock()
_last_warmup_at = 0.0
_async_last_request_at: dict[str, float] = {}
_async_running: set[str] = set()

_NEWS_PRIORITY = [
    "F",
    "AAL",
    "PETR4",
    "VALE3",
    "ITUB4",
    "BBDC4",
    "BBAS3",
    "SANB11",
    "BPAC11",
    "AAPL",
    "MSFT",
    "NVDA",
    "TSLA",
    "AMZN",
    "META",
    "GOOGL",
    "AMD",
    "INTC",
    "BTCUSD",
    "ETHUSD",
]


def _clean_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper().replace(".SA", "")


def _dedupe(symbols: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for symbol in symbols:
        value = _clean_symbol(symbol)
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _read_requests() -> dict[str, dict]:
    try:
        if not REQUEST_PATH.exists():
            return {}
        payload = REQUEST_PATH.read_text(encoding="utf-8")
        if not payload.strip():
            return {}
        data = __import__("json").loads(payload)
        if not isinstance(data, dict):
            return {}
        requests = data.get("requests", data)
        return requests if isinstance(requests, dict) else {}
    except Exception:
        logger.exception("Failed to read news warmup requests")
        return {}


def _write_requests(requests: dict[str, dict]) -> None:
    try:
        REQUEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_path = REQUEST_PATH.with_suffix(".tmp")
        temp_path.write_text(__import__("json").dumps({"requests": requests}, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(REQUEST_PATH)
    except Exception:
        logger.exception("Failed to write news warmup requests")


def request_news_warmup(symbol: str, limit: int = 6) -> None:
    ticker = _clean_symbol(symbol)
    if not ticker:
        return

    item_limit = max(1, min(int(limit or 6), 20))
    key = f"{ticker}:{item_limit}"
    now = time.time()
    should_start_async = False
    with _lock:
        requests = _read_requests()
        current = dict(requests.get(key) or {})
        current.update(
            {
                "symbol": ticker,
                "limit": item_limit,
                "requested_at": now,
                "count": int(current.get("count") or 0) + 1,
            }
        )
        requests[key] = current
        _write_requests(requests)
        last_async = float(_async_last_request_at.get(key) or 0.0)
        if key not in _async_running and now - last_async >= 20.0:
            _async_running.add(key)
            _async_last_request_at[key] = now
            should_start_async = True

    if should_start_async:
        Thread(
            target=_warm_single_request,
            args=(ticker, item_limit, key),
            name=f"news-warmup-{ticker}",
            daemon=True,
        ).start()


def _warm_single_request(symbol: str, limit: int, key: str) -> None:
    start = time.perf_counter()
    success = False
    try:
        if get_cached_symbol_news(symbol, limit=limit):
            success = True
            _drop_warmed_requests([symbol])
            return

        with provider_call_context("news_request_warmup"):
            items = get_symbol_news(symbol, limit=limit)
        success = bool(items)
        if items:
            _drop_warmed_requests([symbol])
    except Exception:
        logger.exception("Async news warmup failed for %s", symbol)
    finally:
        with _lock:
            _async_running.discard(key)
        record_worker_stage_duration("news_request_warmup", time.perf_counter() - start, success=success)


def _requested_symbols() -> list[tuple[str, int]]:
    with _lock:
        requests = _read_requests()
    rows: list[tuple[float, int, str, int]] = []
    for item in requests.values():
        symbol = _clean_symbol(item.get("symbol"))
        if not symbol:
            continue
        limit = max(1, min(int(item.get("limit") or 6), 20))
        rows.append((float(item.get("requested_at") or 0.0), int(item.get("count") or 0), symbol, limit))
    rows.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [(symbol, limit) for _, _, symbol, limit in rows]


def _drop_warmed_requests(symbols: Iterable[str]) -> None:
    warmed = {_clean_symbol(symbol) for symbol in symbols if _clean_symbol(symbol)}
    if not warmed:
        return
    with _lock:
        requests = _read_requests()
        next_requests = {
            key: value
            for key, value in requests.items()
            if _clean_symbol(value.get("symbol")) not in warmed
        }
        if len(next_requests) != len(requests):
            _write_requests(next_requests)


def warm_news_once(limit: int = DEFAULT_NEWS_WARMUP_LIMIT, max_calls: int = DEFAULT_NEWS_WARMUP_MAX_CALLS) -> dict[str, int]:
    global _last_warmup_at

    now = time.time()
    if now - float(_last_warmup_at or 0.0) < DEFAULT_NEWS_WARMUP_INTERVAL_SECONDS:
        return {"requested": 0, "attempted": 0, "warmed": 0, "cached": 0}

    target_pairs = _requested_symbols()
    for symbol in _dedupe(_NEWS_PRIORITY)[: max(0, int(limit))]:
        pair = (symbol, 6)
        if pair not in target_pairs:
            target_pairs.append(pair)

    if not target_pairs:
        _last_warmup_at = now
        return {"requested": 0, "attempted": 0, "warmed": 0, "cached": 0}

    attempted = 0
    warmed = []
    cached = 0
    start = time.perf_counter()

    with provider_call_context("news_warmup"):
        for symbol, item_limit in target_pairs:
            if attempted >= max_calls:
                break
            if get_cached_symbol_news(symbol, limit=item_limit):
                cached += 1
                warmed.append(symbol)
                continue
            attempted += 1
            items = get_symbol_news(symbol, limit=item_limit)
            if items:
                warmed.append(symbol)

    _drop_warmed_requests(warmed)
    _last_warmup_at = now
    record_worker_stage_duration("news_warmup", time.perf_counter() - start, success=bool(warmed) or cached > 0)
    return {"requested": len(target_pairs), "attempted": attempted, "warmed": len(warmed), "cached": cached}
