# =====================================================
# STOCKNEWSBR BREAKOUT SCANNER (V36 OPTIMIZED)
# =====================================================

import logging
import numpy as np
from typing import List, Dict, Any

logger = logging.getLogger("stocknewsbr.scanner.breakout")


# =====================================================
# CONFIG
# =====================================================

BREAKOUT_THRESHOLD = 2.0


# =====================================================
# SAFE FLOAT
# =====================================================

def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


# =====================================================
# VECTOR BREAKOUT SCAN (ENGINE V36)
# =====================================================

def breakout_scan(features: Dict[str, np.ndarray], matrices: Dict) -> List[Dict]:
    """
    Vectorized breakout scanner used by VectorScannerEngine.
    """

    try:

        if not features:
            return []

        tickers = matrices.get("tickers")

        momentum = features.get("momentum")
        acceleration = features.get("price_acceleration")
        volatility = features.get("volatility")

        if tickers is None or momentum is None:
            return []

        # breakout score
        score = momentum * 2 + (acceleration * 3)

        mask = score > BREAKOUT_THRESHOLD

        indices = np.where(mask)[0]

        if len(indices) == 0:
            return []

        signals = []

        for idx in indices:

            signals.append({
                "symbol": tickers[idx],
                "breakout_score": float(score[idx]),
                "momentum": float(momentum[idx]),
                "acceleration": float(acceleration[idx]) if acceleration is not None else 0.0,
                "volatility": float(volatility[idx]) if volatility is not None else 0.0
            })

        signals.sort(
            key=lambda x: x["breakout_score"],
            reverse=True
        )

        return signals[:20]

    except Exception as e:

        logger.exception("Breakout vector scanner failed: %s", e)

        return []


# =====================================================
# SNAPSHOT BREAKOUT SCANNER (LEGACY SAFE MODE)
# =====================================================

def scan_breakouts(snapshot: List[Dict], limit: int = 20):

    if not snapshot:
        return []

    results = []

    try:

        for asset in snapshot:

            if not isinstance(asset, dict):
                continue

            change_pct = _safe_float(asset.get("change_pct"))

            if change_pct < BREAKOUT_THRESHOLD:
                continue

            results.append({
                "symbol": asset.get("symbol"),
                "price": asset.get("price"),
                "change_pct": change_pct,
                "volume": asset.get("volume")
            })

        results.sort(
            key=lambda x: x["change_pct"],
            reverse=True
        )

        return results[:limit]

    except Exception as e:

        logger.error(f"Breakout scanner error: {e}")

        return []