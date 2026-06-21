# =====================================================
# STOCKNEWSBR MARKET ROUTES (ENGINE CACHE INTEGRATION)
# =====================================================

import logging
import time

from fastapi import APIRouter, Depends, HTTPException

from app.ai.final_decision import ensure_final_decision_rows
from app.ai.institutional_priority import ensure_institutional_priority_rows
from app.ai.institutional_radar import ensure_institutional_radar_rows, institutional_radar_items
from app.cache.snapshot_cache import get_snapshot_signals
from app.dependencies import require_active_plan
from app.services.quote_service import get_cached_quote_payload
from app.services.snapshot_contract import is_actionable_snapshot_row
from app.services.symbol_registry import canonical_symbol

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


@router.get("/quote/{ticker}")
def get_quote(
    ticker: str,
    current_user=Depends(require_active_plan),
):
    ticker = canonical_symbol(ticker)

    if not ticker:
        raise HTTPException(status_code=400, detail="Invalid ticker")

    cached = _get_cached_quote(ticker)

    if cached:
        return {
            **cached,
            "plan": getattr(current_user, "plan", "unknown"),
        }

    quote = get_cached_quote_payload(ticker)
    if not quote or quote.get("price") is None:
        raise HTTPException(status_code=404, detail="Ticker not found")

    payload = {
        "ticker": ticker,
        "price": quote.get("price"),
        "change": quote.get("change"),
        "change_pct": quote.get("change_pct"),
        "volume": quote.get("volume"),
        "high": quote.get("high"),
        "low": quote.get("low"),
        "currency": "BRL" if any(char.isdigit() for char in ticker) and not ticker.endswith("USD") else "USD",
        "source": quote.get("source"),
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
        signals = get_snapshot_signals()
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
        raw_signals = get_snapshot_signals()
        has_radar_contract = any(isinstance(row, dict) and ("radar_prioritization_score" in row or "radar_priority_score" in row) for row in raw_signals)
        signals = ensure_final_decision_rows(ensure_institutional_priority_rows(ensure_institutional_radar_rows(raw_signals)))
        radar_signals = institutional_radar_items(signals, limit=50)
        if not radar_signals and not has_radar_contract:
            radar_signals = [row for row in signals if is_actionable_snapshot_row(row)]
        buckets = {
            "momentum": [],
            "liquidity_sweep": [],
            "bearish": [],
        }

        for row in radar_signals:
            if not isinstance(row, dict):
                continue

            if not is_actionable_snapshot_row(row):
                continue

            signal_name = str(row.get("signal", "")).upper()
            events = " ".join(str(event) for event in row.get("events", []))
            institutional = f"{row.get('radar_reason', '')} {row.get('radar_summary', '')} {row.get('radar_level', '')}"
            haystack = f"{signal_name} {events} {institutional}".upper()

            if "MOMENTUM" in haystack or row.get("radar_level"):
                buckets["momentum"].append(row)

            if "SWEEP" in haystack or "LIQUIDITY" in haystack:
                buckets["liquidity_sweep"].append(row)

            master_direction = str(row.get("master_direction") or "").upper()
            master_score = _safe_float(row.get("master_score_raw", row.get("master_score", row.get("score"))))
            if "BEARISH" in haystack or master_direction == "BEARISH" or master_score <= 30:
                buckets["bearish"].append(row)

        return {
            "momentum": buckets["momentum"][:10],
            "liquidity_sweep": buckets["liquidity_sweep"][:10],
            "bearish": buckets["bearish"][:10],
        }
    except Exception as exc:
        logger.exception("Market radar error: %s", exc)
        raise HTTPException(status_code=500, detail="Radar unavailable")
