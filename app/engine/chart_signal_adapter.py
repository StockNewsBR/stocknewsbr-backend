from app.engine.signal_engine import generate_signals

def chart_signals(symbol):

    signals = generate_signals(symbol)

    chart_events = []

    for s in signals:

        if s["type"] == "BUY":

            chart_events.append({
                "type": "buy",
                "shape": "circle",
                "color": "green",
                "price": s["price"],
                "time": s["time"]
            })

        elif s["type"] == "SELL":

            chart_events.append({
                "type": "sell",
                "shape": "circle",
                "color": "red",
                "price": s["price"],
                "time": s["time"]
            })

        elif s["type"] == "SHORT":

            chart_events.append({
                "type": "short",
                "shape": "square",
                "color": "orange",
                "price": s["price"],
                "time": s["time"]
            })

        elif s["type"] == "COVER":

            chart_events.append({
                "type": "cover",
                "shape": "square",
                "color": "blue",
                "price": s["price"],
                "time": s["time"]
            })

    return chart_events