import logging

logger = logging.getLogger("stocknewsbr.signal_processor")


def normalize_score(score):

    try:

        score = float(score)

        if score < 0:
            return 0

        if score > 100:
            return 100

        return round(score, 2)

    except Exception:
        return 0


def enrich_signal(signal):

    try:

        score = normalize_score(signal.get("score", 0))

        signal["score"] = score

        if score >= 85:

            signal["strength"] = "strong"

        elif score >= 70:

            signal["strength"] = "moderate"

        else:

            signal["strength"] = "weak"

        return signal

    except Exception as e:

        logger.error(f"Signal processing error: {e}")

        return signal


def process_signals(signals):

    if not signals:
        return []

    processed = []

    for s in signals:

        if not isinstance(s, dict):
            continue

        processed.append(enrich_signal(s))

    return processed