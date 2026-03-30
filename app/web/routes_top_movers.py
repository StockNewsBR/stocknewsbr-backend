# =====================================================
# STOCKNEWSBR TOP MOVERS ROUTES (OPTIMIZED)
# =====================================================

from fastapi import APIRouter, Depends
import logging

from app.dependencies import require_channel_access
from app.cache.snapshot_cache import get_snapshot_signals

router = APIRouter(
    prefix="/web",
    tags=["web"],
    dependencies=[Depends(require_channel_access("web"))],
)

logger = logging.getLogger("stocknewsbr.web.top_movers")


@router.get("/top-movers")
def get_top_movers():
    try:
        snapshot = get_snapshot_signals()

        if not snapshot:
            return {
                "gainers": [],
                "losers": [],
                "volume_spikes": [],
            }

        movers_up = []
        movers_down = []
        volume_spikes = []

        for data in snapshot:
            try:
                ticker = data.get("ticker") or data.get("symbol")

                if not ticker:
                    continue

                raw_change = (
                    data.get("change")
                    or data.get("change_pct")
                    or (float(data.get("momentum", 0) or 0) * 100)
                )
                change = float(raw_change)
                volume = float(data.get("volume", 0))
                avg_volume = float(data.get("avg_volume", 0))

                item = {
                    "ticker": ticker,
                    "price": data.get("price"),
                    "change": change,
                }

                if change >= 3:
                    movers_up.append(item)
                elif change <= -3:
                    movers_down.append(item)

                if (avg_volume > 0 and volume > avg_volume * 3) or data.get("smart_money"):
                    volume_spikes.append(
                        {
                            "ticker": ticker,
                            "volume": volume,
                        }
                    )

            except Exception:
                continue

        movers_up.sort(key=lambda row: row["change"], reverse=True)
        movers_down.sort(key=lambda row: row["change"])

        return {
            "gainers": movers_up[:10],
            "losers": movers_down[:10],
            "volume_spikes": volume_spikes[:10],
        }

    except Exception as exc:
        logger.exception("Top movers route error: %s", exc)

        return {
            "gainers": [],
            "losers": [],
            "volume_spikes": [],
        }
