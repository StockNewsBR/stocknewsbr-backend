import logging

from fastapi import APIRouter, Depends

from app.cache.signal_cache import signal_cache
from app.dependencies import require_any_channel_access
from app.engine.trend_breakout_signal_engine import (
    build_trend_breakout_payload,
    resolve_chart_timeframe,
)
from app.market.market_data_loader import get_chart_data
from app.models import User
from app.services.chart_overlay_service import build_chart_overlays


router = APIRouter(tags=["App Chart"])
logger = logging.getLogger("stocknewsbr.app.chart")


def _normalize_chart_ticker(value: str) -> str:
    return str(value or "").upper().strip().replace(".SA", "").replace("-USD", "USD")


@router.get("/chart/{symbol}")
def chart(
    symbol: str,
    interval: str = "1D",
    current_user: User = Depends(require_any_channel_access("app", "web")),
):
    try:
        ticker = symbol.upper()
        data = get_chart_data(ticker, interval)

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
            for row in signal_cache.get_all():
                source_ticker = _normalize_chart_ticker(row.get("ticker") or row.get("symbol"))

                if source_ticker != requested:
                    continue

                signals.append(
                    {
                        "score": row.get("score"),
                        "trend": row.get("trend"),
                        "breakout": row.get("breakout"),
                        "signal": row.get("signal"),
                        "events": row.get("events", []),
                    }
                )
        except Exception:
            logger.exception("App chart failed to read signal cache")

        chart_signal = build_trend_breakout_payload(
            ticker,
            data,
            timeframe=resolve_chart_timeframe(interval),
        )

        if chart_signal:
            signals.append(chart_signal)

        overlays = build_chart_overlays(ticker, data, signals)

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
