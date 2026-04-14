from app.engine.signal_engine import generate_signals


def chart_signals(symbol):
    signals = generate_signals(symbol)
    chart_events = []

    for s in signals:
        event_type = str(s.get("type", "")).upper()
        shape = "circle"
        color = "gray"

        if event_type == "BUY":
            shape = "circle"
            color = "green"
        elif event_type == "SELL":
            shape = "circle"
            color = "red"
        elif event_type == "SHORT":
            shape = "square"
            color = "orange"
        elif event_type == "COVER":
            shape = "diamond"
            color = "blue"
        else:
            continue

        chart_events.append(
            {
                "type": event_type.lower(),
                "shape": shape,
                "color": color,
                "price": s.get("price"),
                "time": s.get("time"),
                "score": s.get("score"),
                "reason": s.get("reason"),
            }
        )

    return chart_events
