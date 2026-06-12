from app.ai.ai_market_heat import generate_heatmap as _generate_heatmap
from app.cache.snapshot_cache import get_snapshot_signals


def generate_market_heatmap(signals=None):
    if signals is None:
        signals = get_snapshot_signals()

    return _generate_heatmap(signals or [])


def generate_heatmap(signals=None):
    return generate_market_heatmap(signals=signals)
