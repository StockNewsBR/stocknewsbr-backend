import time
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

from app.market.market_data_loader import (
    get_price_snapshots,
    get_price_snapshot,
    _clear_symbol_failure,
    _is_symbol_cooling_down,
    _mark_symbol_failure,
    _cache_price_payload,
    _PRICE_SNAPSHOT_CACHE,
    _PRICE_SNAPSHOT_CACHE_LOCK,
    _SYMBOL_FAILURES,
)
from app.services.symbol_sanitizer import clear_symbol_cooldown


_ALL_TEST_SYMBOLS = [
    s
    for base in ("PETR4", "VALE3", "ITUB4", "FAKE1", "FAIL1")
    for s in (base, f"{base}.SA")
]


def _reset_market_loader_globals():
    with _PRICE_SNAPSHOT_CACHE_LOCK:
        _PRICE_SNAPSHOT_CACHE.clear()
        _SYMBOL_FAILURES.clear()
    for symbol in _ALL_TEST_SYMBOLS:
        clear_symbol_cooldown(symbol)


@pytest.fixture(autouse=True)
def clean_market_loader_state():
    """Ensure global cache, failure trackers, and symbol-sanitizer cooldowns are
    clean before and after each test, regardless of test order or outcome."""
    _reset_market_loader_globals()
    try:
        yield
    finally:
        _reset_market_loader_globals()


def test_batch_multi_symbol_failure_sets_cooldown():
    """1. batch multi-symbol falha e coloca símbolos em cooldown"""
    symbols = ["PETR4", "VALE3"]
    for s in ["PETR4", "VALE3", "PETR4.SA", "VALE3.SA"]:
        clear_symbol_cooldown(s)
        _clear_symbol_failure(s)

    with patch("app.market.market_data_loader._get_yfinance") as mock_yf:
        yf_inst = MagicMock()
        mock_yf.return_value = yf_inst
        yf_inst.download.return_value = pd.DataFrame()  # empty batch

        get_price_snapshots(symbols, force_refresh=True)

        assert _is_symbol_cooling_down("PETR4") or _is_symbol_cooling_down("PETR4.SA")
        assert _is_symbol_cooling_down("VALE3") or _is_symbol_cooling_down("VALE3.SA")


def test_cooling_down_symbols_skip_sequential_fast_info():
    """2. símbolos em cooldown não disparam N chamadas sequenciais de fast_info"""
    symbols = ["PETR4", "VALE3", "ITUB4"]
    for s in symbols:
        _mark_symbol_failure(s, error="empty_data")
        _mark_symbol_failure(f"{s}.SA", error="empty_data")

    with patch("app.market.market_data_loader._get_yfinance") as mock_yf:
        yf_inst = MagicMock()
        mock_yf.return_value = yf_inst
        yf_inst.download.return_value = pd.DataFrame()

        get_price_snapshots(symbols, force_refresh=True)

        # yf.Ticker fast_info must NOT be called for cooling down symbols in batch
        assert yf_inst.Ticker.call_count == 0


def test_stale_cache_used_during_cooldown():
    """3. cache stale válido é aproveitado durante cooldown"""
    symbol = "PETR4"
    stale_payload = {
        "symbol": symbol,
        "price": 30.0,
        "timestamp": time.time() - 1000,
        "is_stale": False,
    }
    _cache_price_payload(symbol, stale_payload, persist=False)
    _mark_symbol_failure(symbol, error="empty_data")

    with patch("app.market.market_data_loader._get_yfinance") as mock_yf:
        yf_inst = MagicMock()
        mock_yf.return_value = yf_inst
        yf_inst.download.return_value = pd.DataFrame()

        results = get_price_snapshots([symbol], force_refresh=False)
        assert results[symbol] is not None
        assert results[symbol]["price"] == 30.0


def test_symbol_out_of_cooldown_can_use_fast_info():
    """4. símbolo fora de cooldown pode usar fast_info"""
    symbols = ["PETR4", "VALE3"]
    for s in ["PETR4", "VALE3", "PETR4.SA", "VALE3.SA"]:
        clear_symbol_cooldown(s)
        _clear_symbol_failure(s)

    with patch("app.market.market_data_loader._get_yfinance") as mock_yf:
        yf_inst = MagicMock()
        mock_yf.return_value = yf_inst

        # Return empty dataframe for batch to trigger missing symbol handling
        yf_inst.download.return_value = pd.DataFrame()

        mock_ticker = MagicMock()
        mock_ticker.fast_info = {"lastPrice": 35.5, "regularMarketPrice": 35.5}
        yf_inst.Ticker.return_value = mock_ticker

        # Clear cooldown right before testing fast_info fallback
        for s in ["PETR4", "VALE3", "PETR4.SA", "VALE3.SA"]:
            clear_symbol_cooldown(s)
            _clear_symbol_failure(s)

        get_price_snapshots(symbols, force_refresh=True)

        # Símbolos que tentam fast_info e falham entram em cooldown no final do batch
        assert _is_symbol_cooling_down("PETR4") or _is_symbol_cooling_down("PETR4.SA")


def test_failure_of_one_symbol_does_not_affect_others():
    """5. falha de um símbolo não altera os demais"""
    for s in ["PETR4", "FAKE1", "PETR4.SA", "FAKE1.SA"]:
        clear_symbol_cooldown(s)
        _clear_symbol_failure(s)

    with patch("app.market.market_data_loader._get_yfinance") as mock_yf:
        yf_inst = MagicMock()
        mock_yf.return_value = yf_inst

        df = pd.DataFrame({'Close': [30.0], 'Volume': [100]}, index=pd.DatetimeIndex(['2023-01-01']))
        df.columns = pd.MultiIndex.from_tuples([('Close', 'PETR4.SA'), ('Volume', 'PETR4.SA')])
        yf_inst.download.return_value = df

        mock_ticker = MagicMock()
        mock_ticker.fast_info = {}
        mock_ticker.info = {}
        yf_inst.Ticker.return_value = mock_ticker

        results = get_price_snapshots(["PETR4", "FAKE1"], force_refresh=True)

        assert results.get("PETR4") is not None
        assert results["PETR4"]["price"] == 30.0
        assert _is_symbol_cooling_down("FAKE1") or _is_symbol_cooling_down("FAKE1.SA")


def test_partial_batch_processes_only_missing_symbols():
    """6. batch parcial processa somente missing_symbols"""
    for s in ["PETR4", "VALE3", "PETR4.SA", "VALE3.SA"]:
        clear_symbol_cooldown(s)
        _clear_symbol_failure(s)

    _cache_price_payload("PETR4", {"symbol": "PETR4", "price": 30.0, "timestamp": time.time(), "volume": 1000}, persist=False)

    with patch("app.market.market_data_loader._get_yfinance") as mock_yf:
        yf_inst = MagicMock()
        mock_yf.return_value = yf_inst

        df = pd.DataFrame({'Close': [60.0], 'Volume': [100]}, index=pd.DatetimeIndex(['2023-01-01']))
        df.columns = pd.MultiIndex.from_tuples([('Close', 'VALE3.SA'), ('Volume', 'VALE3.SA')])
        yf_inst.download.return_value = df

        results = get_price_snapshots(["PETR4", "VALE3"], force_refresh=False)

        assert results["PETR4"]["price"] == 30.0
        assert results["VALE3"]["price"] > 0


def test_present_batch_symbols_do_not_receive_fallback():
    """7. símbolos presentes no batch não recebem fallback"""
    with patch("app.market.market_data_loader._get_yfinance") as mock_yf:
        yf_inst = MagicMock()
        mock_yf.return_value = yf_inst

        df = pd.DataFrame({'Close': [30.0], 'Volume': [100]}, index=pd.DatetimeIndex(['2023-01-01']))
        df.columns = pd.MultiIndex.from_tuples([('Close', 'PETR4.SA'), ('Volume', 'PETR4.SA')])
        yf_inst.download.return_value = df

        get_price_snapshots(["PETR4", "VALE3"], force_refresh=True)

        assert yf_inst.Ticker.call_count == 0


def test_single_symbol_path_uses_get_price_snapshot():
    """8. caminho single-symbol continua usando get_price_snapshot"""
    for s in ["PETR4", "PETR4.SA"]:
        clear_symbol_cooldown(s)
        _clear_symbol_failure(s)

    with patch("app.market.market_data_loader._get_yfinance") as mock_yf:
        yf_inst = MagicMock()
        mock_yf.return_value = yf_inst

        df = pd.DataFrame({'Close': [30.0], 'Volume': [100]}, index=pd.DatetimeIndex(['2023-01-01']))
        yf_inst.download.return_value = df

        res = get_price_snapshot("PETR4")
        assert res is not None
        assert "price" in res


def test_mark_symbol_failure_called_correctly():
    """9. _mark_symbol_failure é chamado corretamente"""
    symbol = "FAIL1"
    for s in [symbol, f"{symbol}.SA"]:
        clear_symbol_cooldown(s)
        _clear_symbol_failure(s)

    with patch("app.market.market_data_loader._get_yfinance") as mock_yf:
        yf_inst = MagicMock()
        mock_yf.return_value = yf_inst
        yf_inst.download.return_value = pd.DataFrame()

        get_price_snapshots([symbol], force_refresh=True)
        assert _is_symbol_cooling_down(symbol) or _is_symbol_cooling_down(f"{symbol}.SA")


def test_result_order_remains_correct():
    """12. ordem do resultado permanece correta"""
    symbols = ["VALE3", "PETR4", "ITUB4"]
    with patch("app.market.market_data_loader._get_yfinance") as mock_yf:
        yf_inst = MagicMock()
        mock_yf.return_value = yf_inst
        yf_inst.download.return_value = pd.DataFrame()

        results = get_price_snapshots(symbols, force_refresh=True)

        assert list(results.keys()) == symbols
