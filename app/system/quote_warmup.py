from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import deque
from typing import Iterable

from app.market.market_data_loader import get_chart_data, get_price_snapshots
from app.market.universe_engine_v3 import B3_UNIVERSE, BDR_UNIVERSE, CRYPTO_UNIVERSE, ETF_UNIVERSE, US_UNIVERSE
from app.market.universe_registry import INDEX_PROVIDER_SYMBOLS, universe_registry
from app.services.symbol_sanitizer import (
    is_symbol_on_cooldown,
    mark_symbol_cooldown,
    sanitize_market_symbol,
)
from app.system.system_metrics import provider_call_context, record_worker_stage_duration

logger = logging.getLogger("stocknewsbr.quote_warmup")

DEFAULT_QUOTE_WARMUP_INTERVAL_SECONDS = max(45, int(os.getenv("QUOTE_WARMUP_INTERVAL_SECONDS", "60")))
DEFAULT_QUOTE_WARMUP_LIMIT = max(20, int(os.getenv("QUOTE_WARMUP_LIMIT", "140")))
DEFAULT_QUOTE_WARMUP_CHUNK_SIZE = max(5, int(os.getenv("QUOTE_WARMUP_CHUNK_SIZE", "24")))
DEFAULT_CHART_WARMUP_LIMIT = max(0, int(os.getenv("CHART_WARMUP_LIMIT", "24")))
DEFAULT_QUOTE_COOLDOWN_SECONDS = max(120, int(os.getenv("QUOTE_WARMUP_COOLDOWN_SECONDS", "300")))
DEFAULT_CHART_COOLDOWN_SECONDS = max(120, int(os.getenv("CHART_WARMUP_COOLDOWN_SECONDS", "300")))
DEFAULT_CHART_WARMUP_INTERVALS = [
    item.strip().upper()
    for item in os.getenv("CHART_WARMUP_INTERVALS", "1D,1W,1M,3M,6M,YTD,1Y,ALL").split(",")
    if item.strip()
]

_thread: threading.Thread | None = None
_stop_event = threading.Event()
_lock = threading.RLock()
_request_last_at: dict[str, float] = {}
_request_running: set[str] = set()
_quote_cooldowns: dict[str, float] = {}
_chart_cooldowns: dict[str, float] = {}

_PUBLIC_QUOTE_PRIORITY = [
    "PETR4",
    "VALE3",
    "ITUB4",
    "BBDC4",
    "BBAS3",
    "SANB11",
    "BPAC11",
    "WEGE3",
    "IVVB11",
    "AAPL",
    "MSFT",
    "NVDA",
    "TSLA",
    "AMZN",
    "META",
    "GOOGL",
    "GOOG",
    "F",
    "AAL",
    "BA",
    "AMD",
    "BAC",
    "GS",
    "INTC",
    "JPM",
    "QCOM",
    "TSM",
    "XOM",
    "A",
    "AAPL34",
    "AMD34",
    "INTC34",
    "MSFT34",
    "GOGL34",
    "AMZN34",
    "NVDC34",
    "QCOM34",
    "TSLA34",
    "META34",
    "NFLX34",
    "BTCUSD",
    "ETHUSD",
    "BNBUSD",
    "SOLUSD",
    "BTC-USD",
    "ETH-USD",
]

_PUBLIC_CHART_PRIORITY = [
    "F",
    "AAL",
    "AMD",
    "INTC",
    "AAPL",
    "MSFT",
    "NVDA",
    "TSLA",
    "PETR4",
    "VALE3",
    "ITUB4",
    "BBDC4",
    "BBAS3",
    "SANB11",
    "BPAC11",
    "AAPL34",
    "MSFT34",
    "GOGL34",
    "AMZN34",
    "TSLA34",
    "NVDC34",
    "BTCUSD",
    "ETHUSD",
    "SOLUSD",
]


def _clean_symbol(symbol: str) -> str:
    # The loader accepts provider symbols (^BVSP, BRL=X, NQ=F) everywhere, so warmup
    # must not be stricter than the thing it feeds: rejecting them here marked them
    # "invalid_symbol" and guaranteed their cache stayed cold forever. Plain form is
    # still preferred, so nothing that already resolved changes shape.
    sanitized = sanitize_market_symbol(symbol) or sanitize_market_symbol(symbol, allow_provider_symbols=True)
    if not sanitized and symbol:
        mark_symbol_cooldown(symbol, "invalid_symbol")
    return sanitized or ""


def _dedupe(symbols: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for symbol in symbols:
        value = _clean_symbol(symbol)
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _quote_cooldown_key(symbol: str) -> str:
    return _clean_symbol(symbol)


def _chart_cooldown_key(symbol: str, interval: str) -> str:
    ticker = _clean_symbol(symbol)
    return f"{ticker}:{str(interval or '1D').strip().upper()}" if ticker else ""


def _is_quote_on_cooldown(symbol: str, now: float | None = None) -> bool:
    key = _quote_cooldown_key(symbol)
    if not key:
        return False
    if is_symbol_on_cooldown(key, now=now):
        return True
    current_time = now or time.time()
    with _lock:
        cooldown_until = float(_quote_cooldowns.get(key) or 0.0)
    return cooldown_until > current_time


def _mark_quote_cooldown(symbol: str, seconds: int = DEFAULT_QUOTE_COOLDOWN_SECONDS) -> None:
    key = _quote_cooldown_key(symbol)
    if not key:
        return
    with _lock:
        _quote_cooldowns[key] = time.time() + max(60, int(seconds or DEFAULT_QUOTE_COOLDOWN_SECONDS))


def _is_chart_on_cooldown(symbol: str, interval: str, now: float | None = None) -> bool:
    key = _chart_cooldown_key(symbol, interval)
    if not key:
        return False
    if is_symbol_on_cooldown(key, now=now):
        return True
    current_time = now or time.time()
    with _lock:
        cooldown_until = float(_chart_cooldowns.get(key) or 0.0)
    return cooldown_until > current_time


def _mark_chart_cooldown(symbol: str, interval: str, seconds: int = DEFAULT_CHART_COOLDOWN_SECONDS) -> None:
    key = _chart_cooldown_key(symbol, interval)
    if not key:
        return
    with _lock:
        _chart_cooldowns[key] = time.time() + max(60, int(seconds or DEFAULT_CHART_COOLDOWN_SECONDS))


def public_quote_symbols(limit: int | None = None) -> list[str]:
    # Priority + watchlist (canonical public universes) are website-visible, so the
    # warmup limit must never be able to cut them: a cut symbol renders "sem
    # snapshot" forever because nothing else ever populates its quote cache.
    # Ordering alone is not enough — it only holds while the total fits the limit.
    guaranteed = _dedupe([*INDEX_PROVIDER_SYMBOLS, *_PUBLIC_QUOTE_PRIORITY, *universe_registry.get_all_assets()])
    symbols = _dedupe(
        [
            *guaranteed,
            *B3_UNIVERSE,
            *BDR_UNIVERSE,
            *US_UNIVERSE,
            *CRYPTO_UNIVERSE,
            *ETF_UNIVERSE,
        ]
    )
    if limit is None:
        return symbols
    return symbols[: max(len(guaranteed), int(limit))]


def _chart_symbol_candidates(symbol: str) -> list[str]:
    value = _clean_symbol(symbol)
    candidates = [value]
    if re.match(r"^[A-Z]{4,5}(3|4|5|6|11|34)$", value) or re.match(r"^(WIN|WDO)[FGHJKMNQUVXZ]\d{2}$", value):
        candidates.append(f"{value}.SA")
    if value.endswith("USD"):
        candidates.append(value.replace("USD", "-USD"))
    seen = set()
    result = []
    for candidate in candidates:
        candidate_value = str(candidate or "").strip().upper()
        if candidate_value and candidate_value not in seen:
            seen.add(candidate_value)
            result.append(candidate_value)
    return result


def warm_charts_once(symbols: Iterable[str] | None = None, *, limit: int | None = DEFAULT_CHART_WARMUP_LIMIT) -> dict:
    start = time.perf_counter()
    # Index sparklines are served cache-only, so the indices must survive the limit
    # the same way the quote universe does — a cut index renders an empty sparkline.
    guaranteed = [] if symbols else _dedupe(INDEX_PROVIDER_SYMBOLS)
    target_symbols = _dedupe([*guaranteed, *(symbols or _PUBLIC_CHART_PRIORITY)])
    target_intervals = DEFAULT_CHART_WARMUP_INTERVALS or ["1D"]
    if limit is not None:
        target_symbols = target_symbols[: max(len(guaranteed), int(limit))]

    resolved = 0
    failed = 0
    with provider_call_context("chart_warmup"):
        for symbol in target_symbols:
            for interval in target_intervals:
                if _is_chart_on_cooldown(symbol, interval):
                    continue
                try:
                    rows = []
                    for candidate in _chart_symbol_candidates(symbol):
                        rows = get_chart_data(candidate, interval=interval)
                        if rows:
                            break
                    if rows:
                        resolved += 1
                    else:
                        _mark_chart_cooldown(symbol, interval)
                except Exception as exc:
                    failed += 1
                    _mark_chart_cooldown(symbol, interval)
                    logger.warning("Chart warmup failed | symbol=%s | interval=%s | error=%s", symbol, interval, exc)

    record_worker_stage_duration("chart_warmup", time.perf_counter() - start, success=failed == 0 or resolved > 0)
    return {"requested": len(target_symbols) * len(target_intervals), "resolved": resolved, "failed": failed}


def warm_quotes_once(
    symbols: Iterable[str] | None = None,
    *,
    limit: int | None = None,
    chunk_size: int = DEFAULT_QUOTE_WARMUP_CHUNK_SIZE,
) -> dict:
    start = time.perf_counter()
    target_symbols = _dedupe(symbols or public_quote_symbols(limit))
    if limit is not None:
        target_symbols = target_symbols[: max(0, int(limit))]

    if not target_symbols:
        record_worker_stage_duration("quote_warmup", time.perf_counter() - start, success=True)
        return {"requested": 0, "resolved": 0, "failed_chunks": 0}

    resolved = {}
    failed_chunks = 0
    chunk_size = max(1, int(chunk_size or DEFAULT_QUOTE_WARMUP_CHUNK_SIZE))

    with provider_call_context("quote_warmup"):
        for index in range(0, len(target_symbols), chunk_size):
            chunk = target_symbols[index : index + chunk_size]
            if all(_is_quote_on_cooldown(symbol) for symbol in chunk):
                continue
            try:
                chunk_resolved = get_price_snapshots(chunk, force_refresh=True) or {}
                resolved.update(chunk_resolved)
                if not chunk_resolved:
                    for symbol in chunk:
                        _mark_quote_cooldown(symbol)
            except Exception as exc:
                failed_chunks += 1
                for symbol in chunk:
                    _mark_quote_cooldown(symbol)
                logger.warning("Quote warmup chunk failed | chunk=%s | error=%s", chunk, exc)

    success = failed_chunks == 0 or bool(resolved)
    record_worker_stage_duration("quote_warmup", time.perf_counter() - start, success=success)
    return {"requested": len(target_symbols), "resolved": len(resolved), "failed_chunks": failed_chunks}


def request_quote_warmup(
    symbols: Iterable[str] | str,
    *,
    chunk_size: int = DEFAULT_QUOTE_WARMUP_CHUNK_SIZE,
) -> None:
    target_symbols = _dedupe([symbols] if isinstance(symbols, str) else symbols)
    if not target_symbols:
        return

    key = ",".join(target_symbols[:32])
    now = time.time()
    with _lock:
        last_at = float(_request_last_at.get(key) or 0.0)
        if key in _request_running or now - last_at < 20.0:
            return
        _request_last_at[key] = now
        _request_running.add(key)

    threading.Thread(
        target=_warm_requested_quotes,
        args=(target_symbols, key, chunk_size),
        name=f"stocknewsbr-quote-request-{target_symbols[0]}",
        daemon=True,
    ).start()


# On-demand enqueues are driven by whatever a user types, so they need a ceiling the
# scheduled warmup does not: per-symbol spacing plus a global window cap. Symbols the
# provider does not know get a cooldown by warm_quotes_once, so they are tried once.
_ONDEMAND_SYMBOL_INTERVAL_SECONDS = max(15, int(os.getenv("QUOTE_ONDEMAND_SYMBOL_INTERVAL_SECONDS", "30")))
_ONDEMAND_WINDOW_SECONDS = 60.0
_ONDEMAND_WINDOW_MAX = max(1, int(os.getenv("QUOTE_ONDEMAND_WINDOW_MAX", "10")))
_ondemand_last_at: dict[str, float] = {}
_ondemand_recent: deque[float] = deque()


def request_on_demand_quote_warmup(symbol: str) -> bool:
    """Cache miss for a valid symbol outside the warmup universe -> background fetch.

    Public routes are cache-only, so a symbol nothing warms (ADP, any search hit)
    reports "sem cotação" forever. Returns True when an enqueue actually happened.
    """
    ticker = _clean_symbol(symbol)
    if not ticker or _is_quote_on_cooldown(ticker):
        return False

    now = time.time()
    with _lock:
        if now - float(_ondemand_last_at.get(ticker) or 0.0) < _ONDEMAND_SYMBOL_INTERVAL_SECONDS:
            return False
        while _ondemand_recent and now - _ondemand_recent[0] > _ONDEMAND_WINDOW_SECONDS:
            _ondemand_recent.popleft()
        if len(_ondemand_recent) >= _ONDEMAND_WINDOW_MAX:
            return False
        _ondemand_last_at[ticker] = now
        _ondemand_recent.append(now)

    request_quote_warmup(ticker)
    return True


def _warm_requested_quotes(symbols: list[str], key: str, chunk_size: int) -> None:
    start = time.perf_counter()
    success = False
    try:
        with provider_call_context("quote_request_warmup"):
            stats = warm_quotes_once(symbols=symbols, limit=None, chunk_size=chunk_size)
        success = int(stats.get("resolved") or 0) > 0
    except Exception:
        logger.exception("Requested quote warmup failed | symbols=%s", symbols)
    finally:
        with _lock:
            _request_running.discard(key)
        record_worker_stage_duration("quote_request_warmup", time.perf_counter() - start, success=success)


def _quote_warmup_loop(interval_seconds: int, limit: int, chunk_size: int):
    logger.info("Quote warmup started | interval=%ss | limit=%s", interval_seconds, limit)
    while not _stop_event.is_set():
        try:
            stats = warm_quotes_once(limit=limit, chunk_size=chunk_size)
            chart_stats = warm_charts_once(limit=DEFAULT_CHART_WARMUP_LIMIT)
            logger.info(
                "Quote warmup completed | requested=%s | resolved=%s | failed_chunks=%s | charts=%s/%s",
                stats.get("requested"),
                stats.get("resolved"),
                stats.get("failed_chunks"),
                chart_stats.get("resolved"),
                chart_stats.get("requested"),
            )
        except Exception:
            logger.exception("Quote warmup loop error")

        if _stop_event.wait(max(30, int(interval_seconds or DEFAULT_QUOTE_WARMUP_INTERVAL_SECONDS))):
            break

    logger.info("Quote warmup stopped")


def start_quote_warmup(
    *,
    interval_seconds: int = DEFAULT_QUOTE_WARMUP_INTERVAL_SECONDS,
    limit: int = DEFAULT_QUOTE_WARMUP_LIMIT,
    chunk_size: int = DEFAULT_QUOTE_WARMUP_CHUNK_SIZE,
) -> bool:
    global _thread
    with _lock:
        if _thread and _thread.is_alive():
            return False
        _stop_event.clear()
        _thread = threading.Thread(
            target=_quote_warmup_loop,
            args=(interval_seconds, limit, chunk_size),
            name="stocknewsbr-quote-warmup",
            daemon=True,
        )
        _thread.start()
        return True


def stop_quote_warmup(timeout: float = 3.0) -> None:
    with _lock:
        _stop_event.set()
        thread = _thread
    if thread and thread.is_alive():
        thread.join(timeout=timeout)
