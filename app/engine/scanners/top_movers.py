# =====================================================
# STOCKNEWSBR TOP MOVERS SCANNER (V36 OPTIMIZED)
# =====================================================

import logging
import numpy as np
from typing import List, Dict, Any

logger = logging.getLogger("stocknewsbr.scanner.top_movers")

DEFAULT_LIMIT = 20


# =====================================================
# SAFE FLOAT
# =====================================================

def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


# =====================================================
# VECTOR TOP MOVERS (ENGINE V36)
# =====================================================

def top_movers_scan(features: Dict[str, np.ndarray], matrices: Dict) -> List[Dict]:
    """
    Vectorized top movers scanner.
    """

    try:

        tickers = matrices.get("tickers")
        momentum = features.get("momentum")
        volatility = features.get("volatility")

        if tickers is None or momentum is None:
            return []

        score = np.abs(momentum) + (volatility * 0.5)

        idx = np.argsort(score)[::-1]

        results = []

        for i in idx[:DEFAULT_LIMIT]:

            results.append({
                "symbol": tickers[i],
                "move_score": float(score[i]),
                "momentum": float(momentum[i]),
                "volatility": float(volatility[i]) if volatility is not None else 0.0
            })

        return results

    except Exception as e:

        logger.exception("Top movers vector scan failed: %s", e)

        return []


# =====================================================
# SNAPSHOT TOP MOVERS (LEGACY SAFE MODE)
# =====================================================

def get_top_movers(snapshot: List[Dict], limit: int = DEFAULT_LIMIT) -> List[Dict]:

    if not snapshot:
        return []

    movers = []

    try:

        for asset in snapshot:

            if not isinstance(asset, dict):
                continue

            change_pct = asset.get("change_pct")

            if change_pct is None:

                price = _safe_float(asset.get("price"))
                prev = _safe_float(asset.get("prev_close"))

                if prev > 0:
                    change_pct = (price - prev) / prev * 100
                else:
                    change_pct = 0

            change_pct = _safe_float(change_pct)

            movers.append({
                "symbol": asset.get("symbol"),
                "price": asset.get("price"),
                "change_pct": change_pct,
                "volume": asset.get("volume"),
                "score": abs(change_pct)
            })

        movers.sort(
            key=lambda x: abs(x["change_pct"]),
            reverse=True
        )

        return movers[:limit]

    except Exception as e:

        logger.error(f"Top movers scanner error: {e}")

        return []


# =====================================================
# TOP GAINERS
# =====================================================

def get_top_gainers(snapshot: List[Dict], limit: int = DEFAULT_LIMIT):

    try:

        data = [
            a for a in snapshot
            if isinstance(a, dict)
        ]

        data.sort(
            key=lambda x: _safe_float(x.get("change_pct")),
            reverse=True
        )

        return data[:limit]

    except Exception as e:

        logger.error(f"Top gainers error: {e}")

        return []


# =====================================================
# TOP LOSERS
# =====================================================

def get_top_losers(snapshot: List[Dict], limit: int = DEFAULT_LIMIT):

    try:

        data = [
            a for a in snapshot
            if isinstance(a, dict)
        ]

        data.sort(
            key=lambda x: _safe_float(x.get("change_pct"))
        )

        return data[:limit]

    except Exception as e:

        logger.error(f"Top losers error: {e}")

        return []