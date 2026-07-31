import pytest
import time
import threading
from app.services import symbol_sanitizer
from app.market import market_data_loader
from app.system import symbol_hydration

# We want to test that the eviction policy works as expected.
# Note: The codebase uses FIFO eviction on these dicts (e.g., dict.pop(next(iter(dict)))).
# We must ensure they do not exceed their limits.

def test_symbol_sanitizer_cooldowns_bound():
    symbol_sanitizer.clear_symbol_cooldown("nonexistent") # Ensure lock initialization if any
    with symbol_sanitizer._lock:
        symbol_sanitizer._cooldowns.clear()
    
    # Insert 4200 items (limit is 4096)
    for i in range(4200):
        symbol_sanitizer.mark_symbol_cooldown(f"TEST{i}")
    
    with symbol_sanitizer._lock:
        assert len(symbol_sanitizer._cooldowns) <= 4096
        # The oldest entry (TEST0) should have been evicted
        assert symbol_sanitizer._cooldown_key("TEST0") not in symbol_sanitizer._cooldowns
        # The newest entry (TEST4099) should be present
        assert symbol_sanitizer._cooldown_key("TEST4099") in symbol_sanitizer._cooldowns

    with symbol_sanitizer._lock:
        symbol_sanitizer._cooldowns.clear()

def test_price_snapshot_cache_bound(monkeypatch):
    monkeypatch.setattr(market_data_loader, "_payload_matches_requested_symbol", lambda s, p: True)
    with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
        market_data_loader._PRICE_SNAPSHOT_CACHE.clear()

    for i in range(4200):
        symbol = f"TEST{i}"
        market_data_loader._cache_price_payload(symbol, {"price": 10.0, "symbol": symbol, "requested_symbol": symbol}, persist=False)

    with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
        assert len(market_data_loader._PRICE_SNAPSHOT_CACHE) <= 4096
        missing = [f"TEST{i}" for i in range(4200) if f"TEST{i}" not in market_data_loader._PRICE_SNAPSHOT_CACHE]
        print("MISSING KEYS:", missing)
        # TEST0 should be evicted
        assert market_data_loader._cache_key("TEST0") not in market_data_loader._PRICE_SNAPSHOT_CACHE
        # TEST4099 should be present
        assert market_data_loader._cache_key("TEST4099") in market_data_loader._PRICE_SNAPSHOT_CACHE
        
        # Updating an existing key should not cause eviction
        market_data_loader._PRICE_SNAPSHOT_CACHE.clear()

def test_chart_data_cache_bound():
    with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
        market_data_loader._CHART_DATA_CACHE.clear()

    for i in range(2050):
        symbol = f"TEST{i}"
        market_data_loader._cache_chart_data(symbol, "1D", [], persist=False)

    with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
        assert len(market_data_loader._CHART_DATA_CACHE) <= 2048
        market_data_loader._CHART_DATA_CACHE.clear()

def test_symbol_failures_bound():
    with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
        market_data_loader._SYMBOL_FAILURES.clear()

    for i in range(4200):
        symbol = f"TEST{i}"
        market_data_loader._mark_symbol_failure(symbol, "provider")

    with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
        assert len(market_data_loader._SYMBOL_FAILURES) <= 4096
        market_data_loader._SYMBOL_FAILURES.clear()

def test_symbol_hydration_cache_bound():
    with symbol_hydration._LOCK:
        symbol_hydration._CACHE.clear()
    
    # We patch _persist to avoid disk I/O in the test loop
    old_persist = symbol_hydration._persist
    symbol_hydration._persist = lambda: None
    
    try:
        for i in range(4200):
            symbol = f"TEST{i}"
            symbol_hydration._store(symbol, "1D", status="PENDING")

        with symbol_hydration._LOCK:
            assert len(symbol_hydration._CACHE) <= 4096
            assert symbol_hydration._key("TEST0") not in symbol_hydration._CACHE
            assert symbol_hydration._key("TEST4099") in symbol_hydration._CACHE
    finally:
        symbol_hydration._persist = old_persist
        with symbol_hydration._LOCK:
            symbol_hydration._CACHE.clear()

def test_fifo_eviction_and_update():
    with symbol_hydration._LOCK:
        symbol_hydration._CACHE.clear()
        
    old_persist = symbol_hydration._persist
    symbol_hydration._persist = lambda: None
    
    try:
        for i in range(4096):
            symbol = f"TEST{i}"
            symbol_hydration._store(symbol, "1D", status="PENDING")
            
        with symbol_hydration._LOCK:
            assert len(symbol_hydration._CACHE) == 4096
            
        # Updating an existing key should not increase cardinality and not evict other keys
        symbol_hydration._store("TEST0", "1D", status="DONE")
        
        with symbol_hydration._LOCK:
            assert len(symbol_hydration._CACHE) == 4096
            assert symbol_hydration._CACHE[symbol_hydration._key("TEST0")]["status"] == "DONE"
            
        # Adding a new one will evict the first one (TEST0) since this is FIFO
        symbol_hydration._store("NEW1", "1D", status="PENDING")
        with symbol_hydration._LOCK:
            assert len(symbol_hydration._CACHE) == 4096
            assert symbol_hydration._key("TEST0") not in symbol_hydration._CACHE
    finally:
        symbol_hydration._persist = old_persist
        with symbol_hydration._LOCK:
            symbol_hydration._CACHE.clear()

def test_concurrency_cache_limits():
    old_persist = symbol_hydration._persist
    symbol_hydration._persist = lambda: None
    
    with symbol_hydration._LOCK:
        symbol_hydration._CACHE.clear()

    def worker(start_idx, end_idx):
        for i in range(start_idx, end_idx):
            symbol = f"THREAD{i}"
            symbol_hydration._store(symbol, "1D", status="PENDING")

    threads = []
    for i in range(20):
        t = threading.Thread(target=worker, args=(i*250, (i+1)*250))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()

    with symbol_hydration._LOCK:
        # total inserted = 5000, limit = 4096
        assert len(symbol_hydration._CACHE) <= 4096
        symbol_hydration._CACHE.clear()
    
    symbol_hydration._persist = old_persist

def test_cache_clear_reset():
    # Verify the clear/reset public APIs continue working
    symbol_sanitizer.mark_symbol_cooldown("RESET_ME")
    assert symbol_sanitizer.is_symbol_on_cooldown("RESET_ME")
    symbol_sanitizer.clear_symbol_cooldown("RESET_ME")
    assert not symbol_sanitizer.is_symbol_on_cooldown("RESET_ME")
