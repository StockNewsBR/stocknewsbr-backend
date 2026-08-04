"""Retention policy for runtime/cache/market_charts.json.

_persist_chart_cache() merged disk into memory and never pruned, so the file only ever
grew -- 18.2 MB when this was written, 20.1 MB a few hours later. Every forced reparse
paid for that size, which is what pushed /public/market/bundle past the fixture's client
timeout. Retention is what stops the file growing back.

Every case here runs against a temporary file. The real cache is never the subject.
"""

import json
import time
from pathlib import Path

import pytest

from app.market import market_data_loader


@pytest.fixture
def isolated_chart_cache(tmp_path, monkeypatch):
    cache_file = tmp_path / "market_charts.json"
    monkeypatch.setattr(market_data_loader, "_CHART_CACHE_FILE", cache_file)
    monkeypatch.setattr(market_data_loader, "_CHART_CACHE_LOADED", False)
    monkeypatch.setattr(market_data_loader, "_CHART_CACHE_MTIME", 0.0)
    with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
        market_data_loader._CHART_DATA_CACHE.clear()
    yield cache_file
    with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
        market_data_loader._CHART_DATA_CACHE.clear()


def _entry(age_seconds: float, rows: int = 2) -> dict:
    return {
        "timestamp": time.time() - age_seconds,
        "rows": [{"time": f"t{i}", "close": 1.0 + i, "volume": 10} for i in range(rows)],
    }


def test_recent_entries_are_preserved(isolated_chart_cache):
    charts = {"AAPL:1D": _entry(10), "MSFT:1D": _entry(60)}
    kept = market_data_loader._prune_chart_entries(charts)
    assert set(kept) == {"AAPL:1D", "MSFT:1D"}


def test_expired_entries_are_removed(isolated_chart_cache):
    charts = {
        "FRESH:1D": _entry(10),
        "STALE:1D": _entry(market_data_loader._CHART_CACHE_RETENTION_SECONDS + 3600),
    }
    kept = market_data_loader._prune_chart_entries(charts)
    assert "FRESH:1D" in kept
    assert "STALE:1D" not in kept


def test_invalid_and_corrupt_entries_are_removed(isolated_chart_cache):
    charts = {
        "GOOD:1D": _entry(10),
        "NOT_A_DICT:1D": ["nope"],
        "NO_ROWS:1D": {"timestamp": time.time()},
        "ROWS_NOT_LIST:1D": {"timestamp": time.time(), "rows": {"a": 1}},
        "BAD_TS:1D": {"timestamp": "yesterday", "rows": [{"close": 1.0}]},
    }
    kept = market_data_loader._prune_chart_entries(charts)
    assert set(kept) == {"GOOD:1D"}


def test_live_entries_are_never_dropped_even_when_over_limit(isolated_chart_cache, monkeypatch):
    """Anything currently resident in memory belongs to a live run and must survive."""
    monkeypatch.setattr(market_data_loader, "_CHART_CACHE_MAX_ENTRIES", 3)
    charts = {f"OLD{i}:1D": _entry(100 + i) for i in range(10)}
    charts["LIVE:1D"] = _entry(5000)
    with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
        market_data_loader._CHART_DATA_CACHE["LIVE:1D"] = charts["LIVE:1D"]

    kept = market_data_loader._prune_chart_entries(charts)

    assert "LIVE:1D" in kept
    assert len(kept) <= 3


def test_limit_keeps_the_newest_entries(isolated_chart_cache, monkeypatch):
    monkeypatch.setattr(market_data_loader, "_CHART_CACHE_MAX_ENTRIES", 3)
    charts = {f"S{i}:1D": _entry(1000 - i * 100) for i in range(8)}

    kept = market_data_loader._prune_chart_entries(charts)

    assert len(kept) == 3
    # S7 is the youngest (age 300), S5 the third youngest.
    assert set(kept) == {"S5:1D", "S6:1D", "S7:1D"}


def test_pruning_is_idempotent(isolated_chart_cache):
    charts = {
        "KEEP:1D": _entry(10),
        "DROP:1D": _entry(market_data_loader._CHART_CACHE_RETENTION_SECONDS + 10),
    }
    once = market_data_loader._prune_chart_entries(charts)
    twice = market_data_loader._prune_chart_entries(once)
    assert once == twice


def test_persist_applies_retention_and_writes_atomically(isolated_chart_cache):
    stale_age = market_data_loader._CHART_CACHE_RETENTION_SECONDS + 3600
    isolated_chart_cache.write_text(
        json.dumps({"charts": {"OLD:1D": _entry(stale_age), "KEEP:1D": _entry(30)}}),
        encoding="utf-8",
    )
    with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
        market_data_loader._CHART_DATA_CACHE["NEW:1D"] = _entry(1)

    market_data_loader._persist_chart_cache()

    written = json.loads(isolated_chart_cache.read_text(encoding="utf-8"))["charts"]
    assert "NEW:1D" in written
    assert "KEEP:1D" in written
    assert "OLD:1D" not in written
    # No temporary file left behind by the atomic replace.
    assert not list(Path(isolated_chart_cache).parent.glob("*.tmp"))


def test_file_stops_growing_across_repeated_persists(isolated_chart_cache, monkeypatch):
    monkeypatch.setattr(market_data_loader, "_CHART_CACHE_MAX_ENTRIES", 25)
    sizes = []
    for round_index in range(6):
        with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
            market_data_loader._CHART_DATA_CACHE.clear()
            for i in range(20):
                market_data_loader._CHART_DATA_CACHE[f"R{round_index}S{i}:1D"] = _entry(1, rows=5)
        market_data_loader._persist_chart_cache()
        sizes.append(isolated_chart_cache.stat().st_size)

    # Unbounded growth would make the last size a multiple of the first.
    assert sizes[-1] < sizes[0] * 3, f"cache still growing without bound: {sizes}"


def test_reading_after_pruning_still_returns_valid_rows(isolated_chart_cache):
    with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
        market_data_loader._CHART_DATA_CACHE[market_data_loader._chart_cache_key("AAPL", "1D")] = _entry(5)
    market_data_loader._persist_chart_cache()

    with market_data_loader._PRICE_SNAPSHOT_CACHE_LOCK:
        market_data_loader._CHART_DATA_CACHE.clear()
    market_data_loader._CHART_CACHE_LOADED = False
    market_data_loader._CHART_CACHE_MTIME = 0.0

    rows = market_data_loader.get_cached_chart_data("AAPL", "1D", allow_stale=True)
    assert rows and rows[0]["close"] == 1.0
