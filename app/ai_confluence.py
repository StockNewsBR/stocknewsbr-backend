def calculate_confluence(active_models: int, total_models: int = 12):

    if total_models == 0:
        return {
            "ratio": 0,
            "percentage": 0,
            "level": "None"
        }

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
        "ratio": round(ratio,2),
        "percentage": round(percentage,1),
        "level": level
    }