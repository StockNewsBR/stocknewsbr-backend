# =====================================================
# STOCKNEWSBR CHART ROUTES
# =====================================================

from fastapi import APIRouter, Depends
import logging

from app.dependencies import require_channel_access
from app.engine.signal_engine import build_chart_signal_payload
from app.market.market_data_loader import get_cached_chart_data
from app.cache.signal_cache import signal_cache
from app.services.chart_overlay_service import build_chart_overlays
from app.system.system_metrics import record_cache_access

router = APIRouter(
    prefix="/web",
    tags=["web"],
    dependencies=[Depends(require_channel_access("web"))],
)

logger = logging.getLogger("stocknewsbr.web.chart")


def _normalize_chart_ticker(value: str) -> str:
    return str(value or "").upper().strip().replace(".SA", "").replace("-USD", "USD")


# =====================================================
# CHART DATA
# =====================================================

@router.get("/chart/{ticker}")
def get_chart(ticker: str, interval: str = "1D"):

    try:

        ticker = ticker.upper()
        ohlc = get_cached_chart_data(ticker, interval=interval) or []
        record_cache_access("chart", bool(ohlc), "web_chart")

        if not ohlc:
            return {}


        # ------------------------------------------------
        # SIGNALS
        # ------------------------------------------------

        signals = []

        try:

            all_signals = signal_cache.get_all()
            requested = _normalize_chart_ticker(ticker)

            for s in all_signals:
                source_ticker = _normalize_chart_ticker(s.get("ticker") or s.get("symbol"))

                if source_ticker == requested:

                    signals.append({

                        "score": s.get("score"),
                        "trend": s.get("trend"),
                        "breakout": s.get("breakout"),
                        "signal": s.get("signal"),

                        "events": s.get("events", [])

                    })

        except Exception:
            pass

        chart_signal = build_chart_signal_payload(ticker, ohlc, interval=interval)

        if chart_signal:
            signals.append(chart_signal)

        overlays = build_chart_overlays(ticker, ohlc, signals, interval=interval)

        return {

            "ticker": ticker,
            "interval": interval,

            "ohlc": ohlc,
            "signals": signals,
            "chart_signal": chart_signal,
            "alerts": chart_signal.get("events", []) if chart_signal else [],
            "series": overlays["series"],
            "markers": overlays["markers"],
            "zones": overlays["zones"],
            "summary": overlays["summary"],

        }

    except Exception as e:

        logger.error(f"Chart route error: {e}")

        return {}
