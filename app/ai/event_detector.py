# =====================================================
# STOCKNEWSBR AI EVENT DETECTOR
# Fast + Safe
# =====================================================

import logging

logger = logging.getLogger("stocknewsbr.event_detector")


def detect_events(signal):

    if not isinstance(signal, dict):
        return []

    try:

        events = []

        score = signal.get("score", 0)
        radar = signal.get("radar") or []
        volume = signal.get("volume", 0)
        avg_volume = signal.get("avg_volume", 1)

        if avg_volume and volume > avg_volume * 3:
            events.append("volume_anomaly")

        if isinstance(radar, list) and "smart_money_entry" in radar:
            events.append("institutional_flow")

        if isinstance(score, (int, float)) and score >= 90:
            events.append("momentum_burst")

        return events

    except Exception:

        logger.exception("Event detector error")

        return []