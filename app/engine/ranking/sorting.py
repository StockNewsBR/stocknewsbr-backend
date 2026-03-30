# =====================================================
# SIGNAL SORTING ENGINE
# =====================================================
# Ultra fast sorting for ranking signals
# =====================================================

import logging

logger = logging.getLogger("stocknewsbr.sorting")


# =====================================================
# SORT SIGNALS
# =====================================================

def sort_signals(signals, key="score", limit=50):

    if not signals:
        return []

    try:

        sorted_signals = sorted(

            signals,

            key=lambda x: x.get(key, 0),

            reverse=True

        )

        return sorted_signals[:limit]

    except Exception as e:

        logger.error(f"Sorting error: {e}")

        return []


# =====================================================
# TOP SIGNALS
# =====================================================

def top_signals(signals, n=10):

    return sort_signals(signals, limit=n)


# =====================================================
# FILTER BY SCORE
# =====================================================

def filter_by_score(signals, threshold=70):

    if not signals:
        return []

    try:

        return [

            s for s in signals

            if s.get("score", 0) >= threshold

        ]

    except Exception:

        return []