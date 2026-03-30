# =====================================================
# STOCKNEWSBR MOMENTUM SCANNER (V36 OPTIMIZED)
# =====================================================

import logging
import numpy as np
from typing import List, Dict, Any

logger = logging.getLogger("stocknewsbr.scanner.momentum")


# =====================================================
# CONFIG
# =====================================================

MIN_VOLUME = 100000
MOMENTUM_THRESHOLD = 1.2
ACCELERATION_THRESHOLD = 0.6


# =====================================================
# SAFE FLOAT
# =====================================================

def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


# =====================================================
# MOMENTUM SCORE
# =====================================================

def _momentum_score(asset: Dict) -> float:

    change_pct = _safe_float(asset.get("change_pct"))
    volume = _safe_float(asset.get("volume"))
    price = _safe_float(asset.get("price"))

    if volume < MIN_VOLUME or price <= 0:
        return 0.0

    momentum = abs(change_pct)
    acceleration = momentum * 0.5

    return momentum + acceleration


# =====================================================
# VECTOR MOMENTUM SCAN (ENGINE V36)
# =====================================================

def momentum_scan(features: Dict[str, np.ndarray], matrices: Dict) -> List[Dict]:
    """
    Vectorized momentum scanner used by VectorScannerEngine.
    """

    try:

        if not features:
            return []

        momentum = features.get("momentum")
        liquidity = features.get("liquidity_pressure")
        tickers = matrices.get("tickers")

        if momentum is None or tickers is None:
            return []

        scores = momentum + (liquidity * 0.3)

        mask = scores > MOMENTUM_THRESHOLD

        indices = np.where(mask)[0]

        if len(indices) == 0:
            return []

        signals = []

        for idx in indices:

            signals.append({
                "symbol": tickers[idx],
                "momentum_score": float(scores[idx]),
                "momentum": float(momentum[idx]),
                "liquidity_pressure": float(liquidity[idx]) if liquidity is not None else 0.0
            })

        signals.sort(
            key=lambda x: x["momentum_score"],
            reverse=True
        )

        return signals[:25]

    except Exception as e:

        logger.exception("Momentum vector scanner failed: %s", e)

        return []


# =====================================================
# SNAPSHOT MOMENTUM SCANNER (LEGACY SAFE MODE)
# =====================================================

def scan_momentum(snapshot: List[Dict], limit: int = 25):

    if not snapshot:
        return []

    results = []

    try:

        for asset in snapshot:

            if not isinstance(asset, dict):
                continue

            score = _momentum_score(asset)

            if score < MOMENTUM_THRESHOLD:
                continue

            results.append({
                "symbol": asset.get("symbol"),
                "price": asset.get("price"),
                "change_pct": asset.get("change_pct"),
                "volume": asset.get("volume"),
                "momentum_score": score
            })

        results.sort(
            key=lambda x: x["momentum_score"],
            reverse=True
        )

        return results[:limit]

    except Exception as e:

        logger.error(f"Momentum scanner error: {e}")

        return []


# =====================================================
# MOMENTUM ACCELERATION
# =====================================================

def detect_acceleration(snapshot: List[Dict], limit: int = 20):

    if not snapshot:
        return []

    signals = []

    try:

        for asset in snapshot:

            change_pct = _safe_float(asset.get("change_pct"))

            if abs(change_pct) < ACCELERATION_THRESHOLD:
                continue

            signals.append({
                "symbol": asset.get("symbol"),
                "change_pct": change_pct,
                "price": asset.get("price"),
                "volume": asset.get("volume"),
            })

        signals.sort(
            key=lambda x: abs(x["change_pct"]),
            reverse=True
        )

        return signals[:limit]

    except Exception as e:

        logger.error(f"Momentum acceleration error: {e}")

        return []