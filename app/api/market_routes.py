# =====================================================
# STOCKNEWSBR MARKET ROUTES (ENGINE CACHE INTEGRATION)
# =====================================================

import logging
import time

import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException

from app.cache.market_data_cache import market_data_cache
from app.cache.signal_cache import get_all_signals
from app.dependencies import require_active_plan

logger = logging.getLogger("stocknewsbr.market")

router = APIRouter(
    prefix="/market",
    tags=["Market"],
)

QUOTE_CACHE = {}
QUOTE_CACHE_TTL = 30
MAX_CACHE_SIZE = 100


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _get_cached_quote(ticker):
    cached = QUOTE_CACHE.get(ticker)

    if not cached:
        return None

    payload, timestamp = cached

    if time.time() - timestamp > QUOTE_CACHE_TTL:
        QUOTE_CACHE.pop(ticker, None)
        return None

    return payload


def _set_cached_quote(ticker, payload):
    if len(QUOTE_CACHE) >= MAX_CACHE_SIZE:
        QUOTE_CACHE.clear()

    QUOTE_CACHE[ticker] = (payload, time.time())


def get_price_from_engine_cache(ticker):
    try:
        frame = market_data_cache.get(ticker=ticker)

        if frame is None or frame.empty:
            return None

        return float(frame["Close"].iloc[-1])
    except Exception as exc:
        logger.warning("Engine cache price error %s: %s", ticker, exc)
        return None


def get_price_from_yahoo(ticker):
    try:
        history = yf.Ticker(ticker).history(
            period="1d",
            interval="1m",
        )

        if history is None or history.empty:
            return None

        return float(history["Close"].iloc[-1])
    except Exception as exc:
        logger.warning("Yahoo fallback error %s: %s", ticker, exc)
        return None


@router.get("/quote/{ticker}")
def get_quote(
    ticker: str,
    current_user=Depends(require_active_plan),
):
    ticker = ticker.upper().strip()

    if not ticker:
        raise HTTPException(status_code=400, detail="Invalid ticker")

    cached = _get_cached_quote(ticker)

    if cached:
        return {
            **cached,
            "plan": getattr(current_user, "plan", "unknown"),
        }

    price = get_price_from_engine_cache(ticker)

    if price is None:
        price = get_price_from_yahoo(ticker)

    if price is None:
        raise HTTPException(status_code=404, detail="Ticker not found")

    payload = {
        "ticker": ticker,
        "price": price,
        "currency": "BRL" if ticker.endswith(".SA") else "USD",
    }

    _set_cached_quote(ticker, payload)
    return {
        **payload,
        "plan": getattr(current_user, "plan", "unknown"),
    }


@router.get("/top-movers")
def get_top_movers(current_user=Depends(require_active_plan)):
    del current_user

    try:
        signals = get_all_signals()
        movers = []

        for row in signals:
            if not isinstance(row, dict):
                continue

            intensity = abs(
                _safe_float(row.get("change"))
                or _safe_float(row.get("change_pct"))
                or _safe_float(row.get("momentum"))
            )

            item = dict(row)
            item["intensity"] = intensity
            movers.append(item)

        movers.sort(key=lambda item: item["intensity"], reverse=True)

        return {
            "count": len(movers[:20]),
            "movers": movers[:20],
        }
    except Exception as exc:
        logger.exception("Top movers error: %s", exc)
        raise HTTPException(status_code=500, detail="Unable to fetch movers")


@router.get("/radar")
def get_market_radar(current_user=Depends(require_active_plan)):
    del current_user

    try:
        signals = get_all_signals()
        buckets = {
            "momentum": [],
            "liquidity_sweep": [],
            "bearish": [],
        }

        for row in signals:
            if not isinstance(row, dict):
                continue

            signal_name = str(row.get("signal", "")).upper()
            events = " ".join(str(event) for event in row.get("events", []))
            haystack = f"{signal_name} {events}".upper()

            if "MOMENTUM" in haystack:
                buckets["momentum"].append(row)

            if "SWEEP" in haystack or "LIQUIDITY" in haystack:
                buckets["liquidity_sweep"].append(row)

            if "BEARISH" in haystack or _safe_float(row.get("score")) <= 30:
                buckets["bearish"].append(row)

        return {
            "momentum": buckets["momentum"][:10],
            "liquidity_sweep": buckets["liquidity_sweep"][:10],
            "bearish": buckets["bearish"][:10],
        }
    except Exception as exc:
        logger.exception("Market radar error: %s", exc)
        raise HTTPException(status_code=500, detail="Radar unavailable")
