# =====================================================
# STOCKNEWSBR AI MARKET HEATMAP
# Fast + Crash Safe
# =====================================================

import logging

logger = logging.getLogger("stocknewsbr.market_heat")


def sector_heatmap(signals):

    if not signals:
        return {}

    sectors = {}

    try:

        for s in signals:

            if not isinstance(s, dict):
                continue

            sector = s.get("sector") or "unknown"
            score = s.get("score", 0)

            if not isinstance(score, (int, float)):
                continue

            data = sectors.setdefault(sector, {"total": 0.0, "assets": 0})

            data["total"] += score
            data["assets"] += 1

    except Exception:

        logger.exception("Sector heatmap processing error")
        return {}

    result = {}

    try:

        for sector, data in sectors.items():

            assets = data["assets"]

            if assets == 0:
                continue

            avg = data["total"] / assets

            result[sector] = {

                "strength": round(avg, 2),
                "assets": assets

            }

    except Exception:

        logger.exception("Sector normalization error")

    return result


def global_heatmap(signals):

    if not signals:
        return {}

    bullish = bearish = neutral = 0
    total = 0
    count = 0

    try:

        for s in signals:

            if not isinstance(s, dict):
                continue

            score = s.get("score")

            if not isinstance(score, (int, float)):
                continue

            total += score
            count += 1

            if score >= 70:
                bullish += 1

            elif score <= 40:
                bearish += 1

            else:
                neutral += 1

    except Exception:

        logger.exception("Global heatmap error")
        return {}

    if count == 0:
        return {}

    return {

        "market_strength": round(total / count, 2),
        "bullish_assets": bullish,
        "neutral_assets": neutral,
        "bearish_assets": bearish,
        "total_assets": count

    }


def generate_heatmap(signals):

    try:

        return {

            "global": global_heatmap(signals),
            "sectors": sector_heatmap(signals)

        }

    except Exception:

        logger.exception("Heatmap generation error")

        return {

            "global": {},
            "sectors": {}

        }