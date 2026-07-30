from __future__ import annotations

import atexit
import logging
import os
import time
from pathlib import Path
from threading import RLock, Thread
from typing import Iterable

from app.services.news_service import (
    NEWS_CACHE_TTL_SECONDS,
    get_cached_symbol_news,
    get_news_cache_info,
    get_symbol_news,
    normalize_news_locale,
)
from app.services.symbol_sanitizer import (
    is_symbol_on_cooldown,
    mark_symbol_cooldown,
    sanitize_market_symbol,
)
from app.system.system_metrics import provider_call_context, record_worker_stage_duration

logger = logging.getLogger("stocknewsbr.news_warmup")

DEFAULT_NEWS_WARMUP_INTERVAL_SECONDS = max(120, int(os.getenv("NEWS_WARMUP_INTERVAL_SECONDS", "300")))
DEFAULT_NEWS_WARMUP_LIMIT = max(8, int(os.getenv("NEWS_WARMUP_LIMIT", "24")))
DEFAULT_NEWS_WARMUP_MAX_CALLS = max(4, int(os.getenv("NEWS_WARMUP_MAX_CALLS", "12")))
DEFAULT_NEWS_COOLDOWN_SECONDS = max(120, int(os.getenv("NEWS_WARMUP_COOLDOWN_SECONDS", "600")))
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
_symbol_cooldowns: dict[str, float] = {}

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
    sanitized = sanitize_market_symbol(symbol)
    if not sanitized and symbol:
        mark_symbol_cooldown(symbol, "invalid_symbol")
    return sanitized or ""


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


def _is_on_cooldown(symbol: str, now: float | None = None) -> bool:
    ticker = _clean_symbol(symbol)
    if not ticker:
        return False
    if is_symbol_on_cooldown(ticker, now=now):
        return True
    current_time = now if now is not None else time.time()
    with _lock:
        cooldown_until = float(_symbol_cooldowns.get(ticker) or 0.0)
    return cooldown_until > current_time


def _mark_cooldown(symbol: str, seconds: int = DEFAULT_NEWS_COOLDOWN_SECONDS) -> None:
    ticker = _clean_symbol(symbol)
    if not ticker:
        return
    with _lock:
        _symbol_cooldowns[ticker] = time.time() + max(60, int(seconds or DEFAULT_NEWS_COOLDOWN_SECONDS))


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


def request_news_warmup(symbol: str, limit: int = 6, locale: str = "pt-BR") -> bool:
    ticker = _clean_symbol(symbol)
    if not ticker:
        return False

    item_limit = max(1, min(int(limit or 6), 20))
    content_locale = normalize_news_locale(locale)
    key = f"{ticker}:{content_locale}"
    now = time.time()
    should_start_async = False
    is_running = False
    with _lock:
        requests = _read_requests()
        current = dict(requests.get(key) or {})
        current.update(
            {
                "symbol": ticker,
                "limit": max(item_limit, int(current.get("limit") or 0)),
                "locale": content_locale,
                "requested_at": now,
                "count": int(current.get("count") or 0) + 1,
            }
        )
        requests[key] = current
        _write_requests(requests)
        cooldown_until = float(_symbol_cooldowns.get(ticker) or 0.0)
        
        if key in _async_running:
            is_running = True
        elif cooldown_until <= now:
            if len(_async_running) < DEFAULT_NEWS_WARMUP_LIMIT:
                _async_running.add(key)
                _async_last_request_at[key] = now
                should_start_async = True
                is_running = True

    if should_start_async:
        try:
            Thread(
                target=_warm_single_request,
                args=(ticker, item_limit, content_locale, key),
                name=f"news-warmup-{ticker}",
                daemon=True,
            ).start()
        except Exception:
            with _lock:
                _async_running.discard(key)
                _async_last_request_at.pop(key, None)
            logger.exception("Failed to start async news warmup thread for %s", ticker)
            return False

    return is_running


def _warm_single_request(symbol: str, limit: int, locale: str, key: str) -> None:
    start = time.perf_counter()
    success = False
    try:
        cache_info = get_news_cache_info(symbol, locale=locale)
        cache_age = cache_info.get("age_seconds")
        if get_cached_symbol_news(symbol, limit=limit, locale=locale) and cache_age is not None and cache_age < NEWS_CACHE_TTL_SECONDS:
            success = True
            _drop_warmed_requests([symbol])
            return

        with provider_call_context("news_request_warmup"):
            items = get_symbol_news(symbol, limit=limit, locale=locale)
        success = bool(items)
        if items:
            _drop_warmed_requests([symbol])
        else:
            _mark_cooldown(symbol)
    except Exception:
        # Don't mark cooldown on provider exception (R5: allow immediate retry)
        logger.exception("Async news warmup failed for %s", symbol)
        with _lock:
            # Allow immediate retry on failure
            _async_last_request_at.pop(key, None)
    finally:
        with _lock:
            _async_running.discard(key)
        record_worker_stage_duration("news_request_warmup", time.perf_counter() - start, success=success)


def _graceful_shutdown() -> None:
    """Signal all warmup threads to stop and wait briefly for completion."""
    with _lock:
        _shutdown_requested = True
    # Give running threads a moment to notice and exit
    deadline = time.time() + 2.0
    while time.time() < deadline:
        with _lock:
            if not _async_running:
                break
        time.sleep(0.05)


# Register shutdown handler only once
atexit.register(_graceful_shutdown)


_shutdown_requested = False


def _requested_symbols() -> list[tuple[str, int, str]]:
    with _lock:
        requests = _read_requests()
    rows: list[tuple[float, int, str, int, str]] = []
    for item in requests.values():
        symbol = _clean_symbol(item.get("symbol"))
        if not symbol:
            continue
        limit = max(1, min(int(item.get("limit") or 6), 20))
        rows.append((float(item.get("requested_at") or 0.0), int(item.get("count") or 0), symbol, limit, normalize_news_locale(item.get("locale"))))
    rows.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [(symbol, limit, locale) for _, _, symbol, limit, locale in rows]


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
        pair = (symbol, 6, "pt-BR")
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
        for target in target_pairs:
            symbol, item_limit, *requested_locale = target
            locale = normalize_news_locale(requested_locale[0] if requested_locale else "pt-BR")
            if attempted >= max_calls:
                break
            if _is_on_cooldown(symbol, now):
                continue
            cache_info = get_news_cache_info(symbol, locale=locale)
            cache_age = cache_info.get("age_seconds")
            if get_cached_symbol_news(symbol, limit=item_limit, locale=locale) and cache_age is not None and cache_age < NEWS_CACHE_TTL_SECONDS:
                cached += 1
                warmed.append(symbol)
                continue
            attempted += 1
            try:
                items = get_symbol_news(symbol, limit=item_limit, locale=locale)
                if items:
                    warmed.append(symbol)
                else:
                    _mark_cooldown(symbol)
            except Exception:
                # Don't mark cooldown on provider exception (R5: allow immediate retry)
                logger.warning("News warmup failed | symbol=%s | limit=%s", symbol, item_limit)
                # Allow immediate retry by not setting cooldown

    _drop_warmed_requests(warmed)
    _last_warmup_at = now
    record_worker_stage_duration("news_warmup", time.perf_counter() - start, success=bool(warmed) or cached > 0)
    return {"requested": len(target_pairs), "attempted": attempted, "warmed": len(warmed), "cached": cached}
