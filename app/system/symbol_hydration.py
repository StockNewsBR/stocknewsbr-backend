from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock, Thread
from typing import Any

import pandas as pd

from app.market.market_data_loader import get_cached_chart_data
from app.services.news_service import NEWS_CACHE_TTL_SECONDS, get_news_cache_info, normalize_news_locale
from app.services.public_market_data_service import (
    build_public_rsi_contract,
    cached_price_payloads,
    public_daily_freshness_status,
)
from app.services.symbol_registry import canonical_symbol, canonical_symbol_aliases, symbol_category

logger = logging.getLogger("stocknewsbr.symbol_hydration")
_CACHE_PATH = Path(os.getenv("SYMBOL_ANALYSIS_CACHE_FILE") or Path(__file__).resolve().parents[2] / "runtime" / "cache" / "symbol_analysis.json")
_TTL_SECONDS = 120
_WORKER_TIMEOUT_SECONDS = 12
_TERMINAL_STATUSES = {"INSUFFICIENT_DATA", "UNSUPPORTED", "PROVIDER_ERROR", "ERROR"}
_LOCK = RLock()
_RUNNING: set[str] = set()
_CACHE: dict[str, dict[str, Any]] = {}
_LOADED = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deadline_at(started_at: str) -> str:
    started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return (started + timedelta(seconds=_WORKER_TIMEOUT_SECONDS)).isoformat()


def _symbol(value: str) -> str:
    return canonical_symbol(value) or str(value or "").upper().strip()


def _key(symbol: str, timeframe: str = "1D") -> str:
    return f"{_symbol(symbol)}:{str(timeframe or '1D').upper().strip()}"


def _load() -> None:
    global _LOADED
    with _LOCK:
        if _LOADED:
            return
        # Tests must not inherit an on-demand result created by a previous run.
        cache_path = _CACHE_PATH
        if os.getenv("PYTEST_CURRENT_TEST") or "pytest" in " ".join(os.sys.argv).lower():
            cache_path = Path("/tmp") / f"stocknewsbr-symbol-analysis-{os.getpid()}.json"
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _CACHE.update({key: value for key, value in data.get("items", data).items() if isinstance(value, dict)})
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        _LOADED = True


def _persist() -> None:
    try:
        cache_path = _CACHE_PATH
        if os.getenv("PYTEST_CURRENT_TEST") or "pytest" in " ".join(os.sys.argv).lower():
            cache_path = Path("/tmp") / f"stocknewsbr-symbol-analysis-{os.getpid()}.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"items": _CACHE}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(cache_path)
    except OSError:
        logger.exception("Failed to persist on-demand symbol analysis")


def get_symbol_analysis(symbol: str, timeframe: str = "1D") -> dict[str, Any]:
    _load()
    with _LOCK:
        return dict(_CACHE.get(_key(symbol, timeframe)) or {})


def resolve_symbol_context(symbol: str, timeframe: str = "1D") -> dict[str, Any]:
    """One cache-only source of truth for the selected-symbol page."""
    analysis = get_symbol_analysis(symbol, timeframe)
    insight = analysis.get("insight") if isinstance(analysis.get("insight"), dict) else {}
    return {
        "symbol": _symbol(symbol), "timeframe": str(timeframe or "1D").upper(),
        "generated_at": analysis.get("updated_at"), "as_of": analysis.get("as_of"),
        "source": analysis.get("source") or "on_demand",
        "status": analysis.get("status") or "PENDING",
        "data_quality": insight.get("data_quality"), "analysis": analysis,
    }


def _store(symbol: str, timeframe: str, **entry: Any) -> dict[str, Any]:
    _load()
    payload = {"symbol": _symbol(symbol), "timeframe": str(timeframe or "1D").upper(), "updated_at": _now(), "source": "on_demand", **entry}
    with _LOCK:
        key = _key(symbol, timeframe)
        previous = _CACHE.get(key) or {}
        for field in ("started_at", "deadline_at", "retry_count"):
            if field not in entry and previous.get(field) is not None:
                payload[field] = previous[field]
        if key not in _CACHE and len(_CACHE) >= 4096:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = payload
        _persist()
    return payload


def _aliases(symbol: str) -> list[str]:
    ticker = _symbol(symbol)
    return list(dict.fromkeys([ticker, *canonical_symbol_aliases(ticker)]))


def _quote(symbol: str) -> dict[str, Any]:
    for value in cached_price_payloads(_aliases(symbol), allow_stale=False).values():
        if isinstance(value, dict) and float(value.get("price") or 0) > 0:
            return value
    return {}


def _chart(symbol: str, interval: str) -> list[dict[str, Any]]:
    for alias in _aliases(symbol):
        rows = get_cached_chart_data(alias, interval)
        if rows:
            return [row for row in rows if isinstance(row, dict)]
    return []


def _analysis_input(symbol: str, intraday: list[dict[str, Any]], daily: list[dict[str, Any]], quote: dict[str, Any]) -> dict[str, Any] | None:
    if len([row for row in daily if float(row.get("close") or 0) > 0]) < 15 or len(intraday) < 15:
        return None
    frame = pd.DataFrame(
        [{"Open": row.get("open"), "High": row.get("high"), "Low": row.get("low"), "Close": row.get("close"), "Volume": row.get("volume")} for row in intraday]
    )
    if frame.empty or float(frame["Volume"].fillna(0).iloc[-1] or 0) <= 0:
        return None
    from app.engine.market_snapshot_engine import _build_feature_seed

    seed = _build_feature_seed(_symbol(symbol), frame, {"ticker": _symbol(symbol), "score": 50.0, "source": "on_demand"})
    as_of = intraday[-1].get("time") or intraday[-1].get("timestamp")
    daily_rsi = build_public_rsi_contract(_symbol(symbol), "@1D", daily)
    seed.update({
        "as_of": as_of, "market_data_updated_at": as_of, "last_bar_at": as_of,
        "rsi": daily_rsi.get("rsi"), "rsi_timeframe": "1d",
        "daily_as_of": (daily_rsi.get("rsi_metadata") or {}).get("as_of"),
    })
    if float(quote.get("price") or 0) > 0:
        seed["price"] = float(quote["price"])
        seed["change_pct"] = float(quote.get("change_pct") or seed.get("change_pct") or 0)
    return seed


def _gate_decision(payload: dict[str, Any]) -> dict[str, Any]:
    """An incomplete selected-symbol analysis must never authorize a trade."""
    signal = next((row for row in payload.get("signals", []) if isinstance(row, dict)), None)
    panel = payload.get("strategic_panel") if isinstance(payload.get("strategic_panel"), dict) else {}
    tools = payload.get("ai_tools") if isinstance(payload.get("ai_tools"), dict) else {}
    raw_confidence = (panel or signal or {}).get("confidence_pct")
    if raw_confidence is None:
        raw_confidence = (panel or signal or {}).get("confidence")
    try:
        confidence = float(raw_confidence) if raw_confidence is not None else None
    except (TypeError, ValueError):
        confidence = None
    reasons = []
    if not any(isinstance(row, dict) for row in tools.get("institutional_flow", [])):
        reasons.append("fluxo institucional sem leitura atual")
    if not any(isinstance(row, dict) for row in tools.get("liquidity", [])):
        reasons.append("liquidez sem leitura atual")
    if confidence is None:
        reasons.append("confiança operacional não confirmada")
    elif confidence < 50:
        reasons.append("confiança abaixo do limite operacional")
    if not reasons:
        return payload
    for item in (signal, panel):
        if not isinstance(item, dict):
            continue
        item.update({
            "recommended_action": "AGUARDAR", "final_decision": "AGUARDAR",
            "decision_ready": False, "can_trade": False,
            "final_decision_blocks": list(dict.fromkeys([*(item.get("final_decision_blocks") or []), *reasons])),
            "final_decision_summary": "AGUARDAR — " + "; ".join(reasons),
        })
        if confidence is None or confidence <= 0:
            item["confidence_pct"] = None
            item["master_confidence_pct"] = None
            if isinstance(item.get("master_score_block"), dict):
                item["master_score_block"] = {**item["master_score_block"], "confidence_pct": None}
    if signal:
        payload["signals"] = [signal, *[row for row in payload.get("signals", [])[1:] if isinstance(row, dict)]]
    if panel:
        payload["strategic_panel"] = panel
        payload["strategic_panels"] = [panel]
    return payload


def _run(symbol: str, timeframe: str) -> None:
    key = _key(symbol, timeframe)
    try:
        for _ in range(_WORKER_TIMEOUT_SECONDS):
            quote = _quote(symbol)
            intraday = _chart(symbol, "1D")
            daily = _chart(symbol, "3M")
            # Quote is optional: _analysis_input builds the seed from candles alone. Many B3
            # symbols never get a cached quote, so requiring it here left every one of them stuck
            # in INSUFFICIENT_DATA with no strategic_panel -- i.e. the same "AGUARDAR" template
            # for a rising and a falling stock. Candles (with closes) are what the panel needs.
            if intraday and daily:
                seed = _analysis_input(symbol, intraday, daily, quote)
                if seed is None:
                    missing_components = []
                    if len([row for row in daily if float(row.get("close") or 0) > 0]) < 15:
                        missing_components.extend(("chart_daily", "rsi"))
                    if len(intraday) < 15:
                        missing_components.append("chart_intraday")
                    elif float((intraday[-1] or {}).get("volume") or 0) <= 0:
                        missing_components.append("intraday_volume")
                    _store(
                        symbol, timeframe, status="INSUFFICIENT_DATA",
                        reason="insufficient_provider_candles_or_volume",
                        missing_components=list(dict.fromkeys(missing_components)),
                        as_of=daily[-1].get("time"),
                    )
                    return
                from app.engine.market_snapshot_engine import build_snapshot_payload

                payload = _gate_decision(build_snapshot_payload([seed], source="on_demand"))
                for rows in (payload.get("ai_tools") or {}).values():
                    for row in rows if isinstance(rows, list) else []:
                        if isinstance(row, dict):
                            row["analysis_timeframe"] = str(timeframe or "1D").upper()
                            row["candle_timeframe"] = "5m"
                            row["as_of"] = intraday[-1].get("time") or intraday[-1].get("timestamp")
                signal = (payload.get("signals") or [{}])[0]
                _store(
                    symbol,
                    timeframe,
                    status="READY",
                    reason=None,
                    as_of=intraday[-1].get("time") or intraday[-1].get("timestamp"),
                    ai_tools=payload.get("ai_tools") or {},
                    insight=signal if isinstance(signal, dict) else {},
                    strategic_panel=payload.get("strategic_panel") or {},
                )
                return
            time.sleep(1)
        missing_components = [
            name
            for name, available in (("quote", quote), ("chart_intraday", intraday), ("chart_daily", daily))
            if not available
        ]
        _store(
            symbol,
            timeframe,
            status="INSUFFICIENT_DATA",
            reason="hydration_timeout_missing_dependencies",
            missing_components=missing_components,
        )
    except Exception:
        logger.exception("On-demand analysis failed for %s", symbol)
        _store(symbol, timeframe, status="PROVIDER_ERROR", reason="analysis_worker_failed")
    finally:
        with _LOCK:
            _RUNNING.discard(key)


def request_symbol_hydration(symbol: str, *, timeframe: str = "1D", locale: str = "pt-BR", news_limit: int = 6) -> bool:
    """Queue all cache-only bundle dependencies; workers own provider access."""
    ticker = _symbol(symbol)
    if not ticker:
        return False
    _load()
    content_locale = normalize_news_locale(locale)
    from app.system.chart_warmup import request_on_demand_chart_warmup
    from app.system.news_warmup import request_news_warmup
    from app.system.quote_warmup import request_on_demand_quote_warmup

    request_on_demand_quote_warmup(ticker)
    # @5M (multi-day 5m) is required by the comparable intraday-RVOL component. Warming it only
    # for crypto is why equities never got that component -> auditor blocked -> same NEUTRAL verdict.
    chart_intervals = ["1D", "3M", timeframe, "@5M"]
    request_on_demand_chart_warmup(ticker, tuple(dict.fromkeys(chart_intervals)))
    request_news_warmup(ticker, limit=news_limit, locale=content_locale)
    key = _key(ticker, timeframe)
    with _LOCK:
        if key in _RUNNING:
            return False
        current = _CACHE.get(key) or {}
        if str(current.get("status") or "").upper() in {"READY", *_TERMINAL_STATUSES}:
            try:
                updated_at = datetime.fromisoformat(str(current.get("updated_at") or "").replace("Z", "+00:00"))
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - updated_at).total_seconds() < _TTL_SECONDS:
                    return False
            except (TypeError, ValueError):
                pass
        _RUNNING.add(key)
    started_at = _now()
    try:
        retry_count = int(current.get("retry_count") or 0) + 1
    except (TypeError, ValueError):
        retry_count = 1
    _store(
        ticker, timeframe, status="PENDING", reason="hydrating",
        started_at=started_at, deadline_at=_deadline_at(started_at), retry_count=retry_count,
    )
    Thread(target=_run, args=(ticker, timeframe), name=f"symbol-analysis-{ticker}", daemon=True).start()
    return True


def hydration_status(symbol: str, *, timeframe: str = "1D", locale: str = "pt-BR") -> dict[str, str]:
    quote = _quote(symbol)
    intraday = _chart(symbol, "1D")
    daily = _chart(symbol, "3M")
    analysis = get_symbol_analysis(symbol, timeframe)
    news_info = get_news_cache_info(symbol, locale=normalize_news_locale(locale))
    news_age = news_info.get("age_seconds")
    news = "READY" if news_age is not None and news_age < NEWS_CACHE_TTL_SECONDS else "REFRESHING"
    if news_info.get("provider_error"):
        news = "PROVIDER_ERROR"
    elif news_info.get("provider_status") in {"empty", "no_news"} and news_age is not None:
        news = "EMPTY"
    session_date = quote.get("quote_time") or quote.get("market_data_updated_at") or quote.get("updated_at")
    rsi = public_daily_freshness_status(daily, session_date)
    statuses = {
        "quote": "READY" if quote else "PENDING",
        "chart_intraday": "READY" if intraday else "PENDING",
        "chart_daily": "READY" if daily else "PENDING",
        "rsi": rsi,
        "news": news,
        "ai": str(analysis.get("status") or "PENDING"),
    }
    terminal_status = str(analysis.get("status") or "").upper()
    if terminal_status in _TERMINAL_STATUSES:
        missing = set(analysis.get("missing_components") or [])
        for component in ("quote", "chart_intraday", "chart_daily", "rsi"):
            if component in missing or component == "rsi" and "chart_daily" in missing:
                statuses[component] = terminal_status
    return statuses
