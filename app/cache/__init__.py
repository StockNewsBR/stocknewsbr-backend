try:
    from app.cache.market_data_cache import get_cache, get_market_data, market_data_cache
except Exception:
    get_cache = None
    get_market_data = None
    market_data_cache = None

from app.cache.market_snapshot_cache import get_snapshot, get_snapshot_info
from app.cache.signal_cache import get_all_signals, get_signal_info, signal_cache
from app.cache.signal_cache_layer import (
    get_signal_cache,
    get_top_signals,
    update_signal_cache,
)

# Mission 31F: re-exportar a instância com o mesmo nome do submódulo
# sombreava app.cache.signal_cache_layer no pacote e quebrava alvos de
# unittest.mock.patch. O nome do pacote agora aponta para o submódulo.
import app.cache.signal_cache_layer as signal_cache_layer  # noqa: E402,F401
from app.cache.snapshot_cache import (
    get_snapshot_by_ticker,
    get_snapshot_signals,
    update_snapshot,
)

__all__ = [
    "get_cache",
    "get_market_data",
    "market_data_cache",
    "get_snapshot",
    "get_snapshot_by_ticker",
    "get_snapshot_info",
    "get_snapshot_signals",
    "get_signal_cache",
    "get_signal_info",
    "get_top_signals",
    "get_all_signals",
    "signal_cache",
    "signal_cache_layer",
    "update_signal_cache",
    "update_snapshot",
]
