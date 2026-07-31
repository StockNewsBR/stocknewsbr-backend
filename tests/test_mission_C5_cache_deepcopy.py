import threading
import time
from app.cache.snapshot_cache import snapshot_cache
from app.cache.signal_cache_layer import signal_cache_layer
from app.cache.paper_trading_cache import paper_trading_cache


def test_snapshot_cache_no_aliasing():
    snapshot_cache.clear()
    payload = {
        "signals": [{"ticker": "PETR4", "master_score": 90}],
        "updated_at": time.time(),
    }
    snapshot_cache.update(payload)

    res1 = snapshot_cache.get()
    res2 = snapshot_cache.get()

    assert res1 is not res2
    assert res1["signals"] is not res2["signals"]

    # Mutating res1 should not affect res2 or the cache
    res1["signals"][0]["master_score"] = 99
    assert res2["signals"][0]["master_score"] == 9.0
    assert snapshot_cache.get()["signals"][0]["master_score"] == 9.0


def test_signal_cache_no_aliasing():
    signal_cache_layer.clear()
    signals = [{"ticker": "VALE3", "score": 85}]
    signal_cache_layer.update(signals)

    res1 = signal_cache_layer.get()
    res2 = signal_cache_layer.get()

    assert res1 is not res2
    if len(res1) > 0 and len(res2) > 0:
        assert res1[0] is not res2[0]

        # Mutating res1 should not affect res2 or the cache
        res1[0]["score"] = 95
        assert res2[0]["score"] == 85
        assert signal_cache_layer.get()[0]["score"] == 85


def test_paper_trading_cache_no_aliasing():
    paper_trading_cache.reset()
    state = paper_trading_cache.get()
    state["metrics"]["total_trades"] = 10
    paper_trading_cache.update(state)

    res1 = paper_trading_cache.get()
    res2 = paper_trading_cache.get()

    assert res1 is not res2
    assert res1["metrics"] is not res2["metrics"]

    res1["metrics"]["total_trades"] = 99
    assert res2["metrics"]["total_trades"] == 10
    assert paper_trading_cache.get()["metrics"]["total_trades"] == 10


def test_snapshot_cache_concurrency():
    snapshot_cache.clear()
    payload = {
        "signals": [{"ticker": f"TICKER{i}", "master_score": 50} for i in range(100)],
        "updated_at": time.time(),
    }
    snapshot_cache.update(payload)

    reads = []
    start_barrier = threading.Barrier(10)

    def reader():
        start_barrier.wait()
        for _ in range(50):
            reads.append(len(snapshot_cache.get()["signals"]))

    threads = [threading.Thread(target=reader) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)
        assert not t.is_alive(), "Thread deadlock detected or failed to finish within timeout"

    # Ensures no deadlocks and all reads succeed without lock starvation
    assert len(reads) == 500
    assert all(r == 100 for r in reads)
