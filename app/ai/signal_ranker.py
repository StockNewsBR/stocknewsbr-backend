# =====================================================
# STOCKNEWSBR SIGNAL RANKER V2
# Ultra Fast
# =====================================================

def rank_signals(signals):

    if not signals or not isinstance(signals, list):
        return []

    try:

        valid = []

        for s in signals:

            if not isinstance(s, dict):
                continue

            change = s.get("change", 0)

            if not isinstance(change, (int, float)):
                change = 0

            s["_sort"] = abs(change)

            valid.append(s)

        valid.sort(key=lambda x: x["_sort"], reverse=True)

        for s in valid:
            s.pop("_sort", None)

        return valid

    except Exception:

        return list(signals)