# =====================================================
# EVENT DETECTION ENGINE
# =====================================================

def detect_events(data, indicators):

    events = {}

    close = data["Close"]
    volume = data["Volume"]

    ema20 = indicators["ema20"]
    ema50 = indicators["ema50"]

    for symbol in close.columns:

        symbol_events = []

        try:

            if ema20[symbol].iloc[-1] > ema50[symbol].iloc[-1]:

                symbol_events.append("trend_up")

            if volume[symbol].iloc[-1] > indicators["volume_mean"][symbol].iloc[-1] * 2:

                symbol_events.append("volume_spike")

        except Exception:
            continue

        if symbol_events:

            events[symbol] = symbol_events

    return events