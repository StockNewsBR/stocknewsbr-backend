# =====================================================
# STOCKNEWSBR CHART ROUTES
# =====================================================

from fastapi import APIRouter, Depends
import logging

from app.dependencies import require_channel_access
from app.market.market_data_loader import get_chart_data
from app.cache.signal_cache import signal_cache
from app.services.chart_overlay_service import build_chart_overlays

router = APIRouter(
    prefix="/web",
    tags=["web"],
    dependencies=[Depends(require_channel_access("web"))],
)

logger = logging.getLogger("stocknewsbr.web.chart")


# =====================================================
# CHART DATA
# =====================================================

@router.get("/chart/{ticker}")
def get_chart(ticker: str, interval: str = "1D"):

    try:

        ticker = ticker.upper()
        ohlc = get_chart_data(ticker, interval=interval)

        if not ohlc:
            return {}


        # ------------------------------------------------
        # SIGNALS
        # ------------------------------------------------

        signals = []

        try:

            all_signals = signal_cache.get_all()

            for s in all_signals:

                if (s.get("ticker") or s.get("symbol")) == ticker:

                    signals.append({

                        "score": s.get("score"),
                        "trend": s.get("trend"),
                        "breakout": s.get("breakout"),

                        "events": s.get("events", [])

                    })

        except Exception:
            pass


        overlays = build_chart_overlays(ticker, ohlc, signals)

        return {

            "ticker": ticker,
            "interval": interval,

            "ohlc": ohlc,
            "signals": signals,
            "series": overlays["series"],
            "markers": overlays["markers"],
            "zones": overlays["zones"],
            "summary": overlays["summary"],

        }

    except Exception as e:

        logger.error(f"Chart route error: {e}")

        return {}
