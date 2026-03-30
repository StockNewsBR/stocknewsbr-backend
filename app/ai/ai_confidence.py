# =====================================================
# STOCKNEWSBR AI CONFIDENCE
# Fast + Safe
# =====================================================

def calculate_confidence(score):

    try:

        if not isinstance(score, (int, float)):
            score = 0

        if score >= 90:
            return {"confidence": 90, "level": "Ultra High"}

        if score >= 80:
            return {"confidence": 80, "level": "Very High"}

        if score >= 70:
            return {"confidence": 70, "level": "High"}

        if score >= 60:
            return {"confidence": 60, "level": "Moderate"}

        return {"confidence": 50, "level": "Low"}

    except Exception:

        return {"confidence": 0, "level": "Unknown"}