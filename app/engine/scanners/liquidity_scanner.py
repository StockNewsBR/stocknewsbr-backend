# =====================================================
# STOCKNEWSBR LIQUIDITY SWEEP SCANNER (V36 OPTIMIZED)
# =====================================================

import logging
import numpy as np
from typing import List, Dict, Any

logger = logging.getLogger("stocknewsbr.scanner.liquidity")


# =====================================================
# CONFIG
# =====================================================

MIN_VOLUME = 150000
SWEEP_THRESHOLD = 1.5


# =====================================================
# SAFE FLOAT
# =====================================================

def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


# =====================================================
# LIQUIDITY SCORE
# =====================================================

def _liquidity_score(asset: Dict) -> float:

    change_pct = _safe_float(asset.get("change_pct"))
    volume = _safe_float(asset.get("volume"))

    if volume < MIN_VOLUME:
        return 0.0

    return abs(change_pct)


# =====================================================
# VECTOR LIQUIDITY SCAN (ENGINE V36)
# =====================================================

def liquidity_scan(features: Dict[str, np.ndarray], matrices: Dict) -> List[Dict]:
    """
    Vectorized liquidity sweep scanner used by VectorScannerEngine.
    """

    try:

        if not features:
            return []

        tickers = matrices.get("tickers")

        momentum = features.get("momentum")
        liquidity_pressure = features.get("liquidity_pressure")
        volatility = features.get("volatility")

        if tickers is None or liquidity_pressure is None:
            return []

        # combined liquidity score
        score = liquidity_pressure + (np.abs(momentum) * 0.5)

        mask = score > SWEEP_THRESHOLD

        indices = np.where(mask)[0]

        if len(indices) == 0:
            return []

        signals = []

        for idx in indices:

            signals.append({
                "symbol": tickers[idx],
                "liquidity_score": float(score[idx]),
                "liquidity_pressure": float(liquidity_pressure[idx]),
                "momentum": float(momentum[idx]) if momentum is not None else 0.0,
                "volatility": float(volatility[idx]) if volatility is not None else 0.0
            })

        signals.sort(
            key=lambda x: x["liquidity_score"],
            reverse=True
        )

        return signals[:20]

    except Exception as e:

        logger.exception("Liquidity vector scanner failed: %s", e)

        return []


# =====================================================
# SNAPSHOT LIQUIDITY SCANNER (LEGACY SAFE MODE)
# =====================================================

def scan_liquidity(snapshot: List[Dict], limit: int = 20):

    if not snapshot:
        return []

    signals = []

    try:

        for asset in snapshot:

            if not isinstance(asset, dict):
                continue

            score = _liquidity_score(asset)

            if score < SWEEP_THRESHOLD:
                continue

            signals.append({
                "symbol": asset.get("symbol"),
                "price": asset.get("price"),
                "change_pct": asset.get("change_pct"),
                "volume": asset.get("volume"),
                "liquidity_score": score
            })

        signals.sort(
            key=lambda x: x["liquidity_score"],
            reverse=True
        )

        return signals[:limit]

    except Exception as e:

        logger.error(f"Liquidity scanner error: {e}")

        return []