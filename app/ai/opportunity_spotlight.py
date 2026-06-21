# =====================================================
# STOCKNEWSBR BEST OPPORTUNITY
# Fast + Crash Safe
# =====================================================

from app.cache.snapshot_cache import get_snapshot_signals
from app.services.snapshot_contract import is_actionable_snapshot_row


def get_best_opportunity():

    try:

        signals = get_snapshot_signals()

        if not signals or not isinstance(signals, list):
            return None

        best = None
        best_score = -1

        for s in signals:

            if not isinstance(s, dict):
                continue

            if not is_actionable_snapshot_row(s):
                continue

            score = s.get("score")

            if not isinstance(score, (int, float)):
                continue

            if score > best_score:
                best = s
                best_score = score

        if not best:
            return None

        return {

            "ticker": best.get("ticker"),
            "score": best_score,
            "price": best.get("price"),
            "signals": best.get("signals", []),
            "timestamp": best.get("timestamp")

        }

    except Exception:

        return None
