def calculate_market_pulse(signals):

    bullish = 0
    bearish = 0

    for s in signals:

        if s["score"] >= 70:
            bullish += 1

        if s["score"] <= 40:
            bearish += 1

    total = len(signals)

    if total == 0:
        return {"bullish":0,"bearish":0}

    return {
        "bullish": round((bullish/total)*100,1),
        "bearish": round((bearish/total)*100,1)
    }