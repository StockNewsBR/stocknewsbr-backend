# =====================================================
# STOCKNEWSBR AI CONFLUENCE
# Fast + Safe
# =====================================================

def calculate_confluence(active_models, total_models=12):

    try:

        if not isinstance(active_models, (int, float)):
            active_models = 0

        if not isinstance(total_models, (int, float)) or total_models <= 0:
            total_models = 1

        ratio = active_models / total_models
        percentage = ratio * 100

        if ratio >= 0.8:
            level = "Ultra High"

        elif ratio >= 0.6:
            level = "High"

        elif ratio >= 0.4:
            level = "Moderate"

        else:
            level = "Low"

        return {

            "ratio": round(ratio, 2),
            "percentage": round(percentage, 1),
            "level": level

        }

    except Exception:

        return {
            "ratio": 0,
            "percentage": 0,
            "level": "None"
        }