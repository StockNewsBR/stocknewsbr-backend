def calculate_signal_strength(score, confluence):

    strength = (score * 0.6) + (confluence["percentage"] * 0.4)

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
        "strength": round(strength,1),
        "level": level
    }