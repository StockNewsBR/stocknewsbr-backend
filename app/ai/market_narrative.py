from app.ai.ai_market_narrative import generate_market_narrative as _generate_market_narrative
from app.ai.market_heatmap import generate_market_heatmap
from app.cache.signal_cache import get_all_signals


def generate_market_narrative(symbol="Market", score=None, confluence=None):
    if score is None or confluence is None:
        signals = get_all_signals()
        heatmap = generate_market_heatmap(signals)
        global_heat = heatmap.get("global", {})

        score = global_heat.get("market_strength", 0)
        confluence = min(10, len([row for row in signals if (row.get("score") or 0) >= 70]))

    return _generate_market_narrative(symbol, score, confluence)
