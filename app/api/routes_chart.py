import logging

from fastapi import APIRouter, Depends

from app.cache.snapshot_cache import get_snapshot_signals
from app.dependencies import require_any_channel_access
from app.engine.signal_engine import build_chart_signal_payload
from app.market.market_data_loader import get_cached_chart_data
from app.models import User
from app.services.chart_overlay_service import build_chart_overlays
from app.services.snapshot_contract import snapshot_surface_row
from app.api.routes_public_market_live import _load_chart_data_fast as load_chart_data_cache_first
from app.system.system_metrics import record_cache_access


router = APIRouter(tags=["App Chart"])
logger = logging.getLogger("stocknewsbr.app.chart")


def _normalize_chart_ticker(value: str) -> str:
    return str(value or "").upper().strip().replace(".SA", "").replace("-USD", "USD")


def _load_chart_data_fast(ticker: str, interval: str):
    cached = get_cached_chart_data(ticker, interval) or load_chart_data_cache_first(ticker, interval)
    record_cache_access("chart", bool(cached), "app_chart")
    return cached or []


@router.get("/chart/{symbol}")
def chart(
    symbol: str,
    interval: str = "1D",
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    try:
        ticker = symbol.upper()
        data = _load_chart_data_fast(ticker, interval)

        if not data:
            return {
                "symbol": ticker,
                "ticker": ticker,
                "interval": interval,
                "data": [],
                "ohlc": [],
                "signals": [],
                "alerts": [],
                "markers": [],
                "zones": [],
                "summary": {},
            }

        requested = _normalize_chart_ticker(ticker)
        signals = []

        try:
            for row in get_snapshot_signals():
                source_ticker = _normalize_chart_ticker(row.get("ticker") or row.get("symbol"))

                if source_ticker != requested:
                    continue

                signals.append(snapshot_surface_row(row))
        except Exception:
            logger.exception("App chart failed to read snapshot cache")

        chart_signal = build_chart_signal_payload(ticker, data, interval=interval)

        if chart_signal:
            signals.append(chart_signal)

        overlays = build_chart_overlays(ticker, data, signals, interval=interval)

        return {
            "symbol": ticker,
            "ticker": ticker,
            "interval": interval,
            "data": data,
            "ohlc": data,
            "signals": signals,
            "chart_signal": chart_signal,
            "alerts": chart_signal.get("events", []) if chart_signal else [],
            "series": overlays["series"],
            "markers": overlays["markers"],
            "zones": overlays["zones"],
            "summary": overlays["summary"],
            "channel": getattr(current_user, "plan", None),
        }
    except Exception as exc:
        logger.exception("App chart route error: %s", exc)
        return {
            "symbol": symbol.upper(),
            "ticker": symbol.upper(),
            "interval": interval,
            "data": [],
            "ohlc": [],
            "signals": [],
            "alerts": [],
            "markers": [],
            "zones": [],
            "summary": {},
        }
