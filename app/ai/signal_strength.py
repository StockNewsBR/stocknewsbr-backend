# =====================================================
# STOCKNEWSBR SIGNAL STRENGTH V2
# =====================================================

import logging

logger = logging.getLogger("stocknewsbr.signal_strength")


def calculate_signal_strength(score, confluence):

    try:

        if not isinstance(score, (int, float)):
            score = 0.0

        percentage = 0.0

        if isinstance(confluence, dict):

            val = confluence.get("percentage")

            if isinstance(val, (int, float)):
                percentage = float(val)

        strength = (score * 0.6) + (percentage * 0.4)

        if strength >= 90:
            level = "Extreme"
        elif strength >= 80:
            level = "Very Strong"
        elif strength >= 70:
            level = "Strong"
        elif strength >= 60:
            level = "Moderate"
        else:
            level = "Weak"

        return {
            "strength": round(strength, 1),
            "level": level
        }

    except Exception:

        logger.exception("Signal strength error")

        return {
            "strength": 0.0,
            "level": "Unknown"
        }