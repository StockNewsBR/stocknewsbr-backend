# =====================================================
# STOCKNEWSBR SIGNAL FUSION ENGINE v2 (PRODUCTION)
# =====================================================
# Multi-factor signal scoring engine
# Optimized for speed and stability
# =====================================================

import logging

logger = logging.getLogger("stocknewsbr.engine.signal_fusion_v2")


# =====================================================
# CONFIG
# =====================================================

WEIGHTS = {
    "momentum": 3.0,
    "breakout": 2.5,
    "liquidity": 2.0,
    "smart_money": 3.5,
    "volume_spike": 1.5
}

MAX_SIGNALS = 500


# =====================================================
# BUILD SCORE
# =====================================================

def compute_score(signal):

    if not isinstance(signal, dict):
        return 0.0

    score = 0.0

    try:

        for key, weight in WEIGHTS.items():

            value = signal.get(key)

            if value:

                score += weight

        return score

    except Exception:

        return 0.0


# =====================================================
# FUSION ENGINE
# =====================================================

def run_signal_fusion(signals):

    if not signals:
        return []

    fused = []

    try:

        for s in signals:

            if not isinstance(s, dict):
                continue

            score = compute_score(s)

            # copy to avoid mutating original signal
            item = dict(s)

            item["fusion_score"] = score

            fused.append(item)

        # limit list size for safety
        if len(fused) > MAX_SIGNALS:
            fused = fused[:MAX_SIGNALS]

        fused.sort(
            key=lambda x: x.get("fusion_score", 0),
            reverse=True
        )

        return fused

    except Exception as e:

        logger.error(f"Signal fusion error: {e}")

        return []