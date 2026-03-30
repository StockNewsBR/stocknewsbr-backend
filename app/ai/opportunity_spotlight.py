# =====================================================
# STOCKNEWSBR BEST OPPORTUNITY
# Fast + Crash Safe
# =====================================================

from app.cache.signal_cache import signal_cache


def get_best_opportunity():

    try:

        signals = signal_cache.get()

        if not signals or not isinstance(signals, list):
            return None

        best = None
        best_score = -1

        for s in signals:

            if not isinstance(s, dict):
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