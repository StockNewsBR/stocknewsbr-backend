# =====================================================
# STOCKNEWSBR SMART MONEY SCANNER (V36 OPTIMIZED)
# =====================================================

import logging
import numpy as np
from typing import List, Dict, Any

logger = logging.getLogger("stocknewsbr.scanner.smart_money")


# =====================================================
# CONFIG
# =====================================================

VOLUME_SPIKE = 2.0


# =====================================================
# SAFE FLOAT
# =====================================================

def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


# =====================================================
# VECTOR SMART MONEY SCAN (ENGINE V36)
# =====================================================

def smart_money_scan(features: Dict[str, np.ndarray], matrices: Dict) -> List[Dict]:
    """
    Vectorized smart money scanner used by VectorScannerEngine.
    Detects abnormal volume pressure.
    """

    try:

        if not features:
            return []

        tickers = matrices.get("tickers")

        liquidity_pressure = features.get("liquidity_pressure")
        volume_spike = features.get("volume_spike")
        momentum = features.get("momentum")

        if tickers is None or liquidity_pressure is None:
            return []

        # smart money score
        score = liquidity_pressure * (np.abs(momentum) + 1)

        mask = score > VOLUME_SPIKE

        indices = np.where(mask)[0]

        if len(indices) == 0:
            return []

        signals = []

        for idx in indices:

            signals.append({
                "symbol": tickers[idx],
                "smart_money_score": float(score[idx]),
                "liquidity_pressure": float(liquidity_pressure[idx]),
                "momentum": float(momentum[idx]) if momentum is not None else 0.0,
                "volume_spike": bool(volume_spike[idx]) if volume_spike is not None else False
            })

        signals.sort(
            key=lambda x: x["smart_money_score"],
            reverse=True
        )

        return signals[:20]

    except Exception as e:

        logger.exception("Smart money vector scanner failed: %s", e)

        return []


# =====================================================
# SNAPSHOT SMART MONEY SCANNER (LEGACY SAFE MODE)
# =====================================================

def scan_smart_money(snapshot: List[Dict], limit: int = 20):

    if not snapshot:
        return []

    signals = []

    try:

        for asset in snapshot:

            if not isinstance(asset, dict):
                continue

            volume = _safe_float(asset.get("volume"))
            avg_volume = _safe_float(asset.get("avg_volume"))

            if avg_volume <= 0:
                continue

            spike = volume / avg_volume

            if spike < VOLUME_SPIKE:
                continue

            signals.append({
                "symbol": asset.get("symbol"),
                "price": asset.get("price"),
                "volume": volume,
                "volume_spike": spike
            })

        signals.sort(
            key=lambda x: x["volume_spike"],
            reverse=True
        )

        return signals[:limit]

    except Exception as e:

        logger.error(f"Smart money scanner error: {e}")

        return []