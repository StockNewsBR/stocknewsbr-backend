from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Iterable

from app.market.market_data_loader import get_chart_data, get_price_snapshots
from app.market.universe_engine_v3 import B3_UNIVERSE, BDR_UNIVERSE, CRYPTO_UNIVERSE, ETF_UNIVERSE, US_UNIVERSE
from app.system.system_metrics import provider_call_context, record_worker_stage_duration

logger = logging.getLogger("stocknewsbr.quote_warmup")

DEFAULT_QUOTE_WARMUP_INTERVAL_SECONDS = max(60, int(os.getenv("QUOTE_WARMUP_INTERVAL_SECONDS", "180")))
DEFAULT_QUOTE_WARMUP_LIMIT = max(20, int(os.getenv("QUOTE_WARMUP_LIMIT", "140")))
DEFAULT_QUOTE_WARMUP_CHUNK_SIZE = max(5, int(os.getenv("QUOTE_WARMUP_CHUNK_SIZE", "24")))
DEFAULT_CHART_WARMUP_LIMIT = max(0, int(os.getenv("CHART_WARMUP_LIMIT", "24")))
DEFAULT_CHART_WARMUP_INTERVALS = [
    item.strip().upper()
    for item in os.getenv("CHART_WARMUP_INTERVALS", "1D,1W,1M,3M,6M,YTD,1Y,ALL").split(",")
    if item.strip()
]

_thread: threading.Thread | None = None
_stop_event = threading.Event()
_lock = threading.RLock()

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
    "A",
    "AAPL34",
    "MSFT34",
    "GOGL34",
    "AMZN34",
    "NVDC34",
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
    return str(symbol or "").strip().upper().replace(".SA", "")


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


def public_quote_symbols(limit: int | None = None) -> list[str]:
    symbols = _dedupe(
        [
            *_PUBLIC_QUOTE_PRIORITY,
            *B3_UNIVERSE,
            *BDR_UNIVERSE,
            *US_UNIVERSE,
            *CRYPTO_UNIVERSE,
            *ETF_UNIVERSE,
        ]
    )
    if limit is None:
        return symbols
    return symbols[: max(0, int(limit))]


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
    target_symbols = _dedupe(symbols or _PUBLIC_CHART_PRIORITY)
    target_intervals = DEFAULT_CHART_WARMUP_INTERVALS or ["1D"]
    if limit is not None:
        target_symbols = target_symbols[: max(0, int(limit))]

    resolved = 0
    failed = 0
    with provider_call_context("chart_warmup"):
        for symbol in target_symbols:
            for interval in target_intervals:
                try:
                    rows = []
                    for candidate in _chart_symbol_candidates(symbol):
                        rows = get_chart_data(candidate, interval=interval)
                        if rows:
                            break
                    if rows:
                        resolved += 1
                except Exception as exc:
                    failed += 1
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
            try:
                resolved.update(get_price_snapshots(chunk) or {})
            except Exception as exc:
                failed_chunks += 1
                logger.warning("Quote warmup chunk failed | chunk=%s | error=%s", chunk, exc)

    success = failed_chunks == 0 or bool(resolved)
    record_worker_stage_duration("quote_warmup", time.perf_counter() - start, success=success)
    return {"requested": len(target_symbols), "resolved": len(resolved), "failed_chunks": failed_chunks}


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
