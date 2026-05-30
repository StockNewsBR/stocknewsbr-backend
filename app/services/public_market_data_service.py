from app.market.market_data_loader import (
    get_cached_chart_data,
    get_cached_price_snapshots,
)
from app.system.system_metrics import record_cache_access


def cached_price_payloads(symbols: list[str], allow_stale: bool = False) -> dict:
    return get_cached_price_snapshots(symbols, allow_stale=allow_stale)


def load_public_chart_rows(aliases: list[str], interval: str, scope: str = "public_market_live") -> list[dict]:
    for alias in aliases:
        cached = get_cached_chart_data(alias, interval)
        if cached:
            record_cache_access("chart", True, scope)
            return cached

    record_cache_access("chart", False, scope)
    return []
