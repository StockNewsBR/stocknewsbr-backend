# =====================================================
# STOCKNEWSBR RANKING ENGINE V2 (V36 OPTIMIZED)
# =====================================================

import logging
import numpy as np
from typing import List, Dict, Any

logger = logging.getLogger("stocknewsbr.engine.ranking")


# =====================================================
# SAFE FLOAT
# =====================================================

def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


# =====================================================
# BUILD RANKING
# =====================================================

def build_ranking(signals: List[Dict]) -> List[Dict]:
    """
    Build ranked signal list.

    Optimized for:
    - large signal sets
    - crash safety
    - fast sorting
    """

    if not signals:
        return []

    try:

        tickers = []
        scores = []
        events = []

        for s in signals:

            try:

                ticker = s.get("symbol") or s.get("ticker")

                if ticker is None:
                    continue

                score = _safe_float(
                    s.get("score")
                    or s.get("momentum_score")
                    or s.get("breakout_score")
                    or s.get("liquidity_score")
                    or s.get("smart_money_score")
                    or s.get("move_score")
                )

                tickers.append(ticker)
                scores.append(score)
                events.append(s.get("events", []))

            except Exception:
                continue

        if not scores:
            return []

        scores_np = np.asarray(scores)

        idx = np.argsort(scores_np)[::-1]

        ranking = []

        for i in idx:

            ranking.append({
                "ticker": tickers[i],
                "score": float(scores_np[i]),
                "events": events[i]
            })

        return ranking

    except Exception as e:

        logger.exception("Ranking engine failure: %s", e)

        return []