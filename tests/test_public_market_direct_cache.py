"""Contract for the memoised direct cache reader in public_market_data_service.

_read_json_cache() used to json.loads() the whole file on every call, and
load_public_chart_rows() calls _direct_cached_chart_data() once per alias -- so a symbol
with ten aliases paid ten full parses of an 18 MB file. The cost was linear in alias
count, which is why BTCUSD (10 aliases) was consistently ~2.5x slower than PETR4 (4).
"""

import json
import threading
import time
from pathlib import Path

import pytest

from app.services import public_market_data_service as service


@pytest.fixture(autouse=True)
def reset_memo():
    service._reset_json_cache()
    yield
    service._reset_json_cache()


@pytest.fixture
def counted_reads(monkeypatch):
    """Count real file reads, whatever the memo decides to do."""
    reads: list[str] = []
    unpatched = Path.read_text

    def counting_read_text(self, *args, **kwargs):
        reads.append(str(self))
        return unpatched(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    return reads


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_first_read_parses_once(tmp_path, counted_reads):
    cache = tmp_path / "charts.json"
    _write(cache, {"charts": {"AAPL:1D": {"timestamp": time.time(), "rows": [{"close": 1.0}]}}})

    assert service._read_json_cache(cache)["charts"]
    assert len(counted_reads) == 1


def test_repeated_reads_of_unchanged_file_do_not_reparse(tmp_path, counted_reads):
    cache = tmp_path / "charts.json"
    _write(cache, {"charts": {"AAPL:1D": {"rows": []}}})

    for _ in range(10):
        service._read_json_cache(cache)

    # Ten aliases must cost one parse, not ten. This is the defect itself.
    assert len(counted_reads) == 1


def test_real_file_change_invalidates_the_memo(tmp_path, counted_reads):
    cache = tmp_path / "charts.json"
    _write(cache, {"charts": {"AAPL:1D": {"rows": []}}})
    assert "AAPL:1D" in service._read_json_cache(cache)["charts"]

    _write(cache, {"charts": {"MSFT:1D": {"rows": []}}})
    refreshed = service._read_json_cache(cache)

    assert "MSFT:1D" in refreshed["charts"]
    assert len(counted_reads) == 2


def test_atomic_replace_is_picked_up(tmp_path, counted_reads):
    """An os.replace() swap must invalidate even when size happens to match."""
    import os

    cache = tmp_path / "charts.json"
    _write(cache, {"charts": {"AAA:1D": {"rows": []}}})
    service._read_json_cache(cache)

    replacement = tmp_path / "next.json"
    _write(replacement, {"charts": {"BBB:1D": {"rows": []}}})
    os.replace(replacement, cache)

    assert "BBB:1D" in service._read_json_cache(cache)["charts"]


def test_consumer_results_are_defensive_copies(tmp_path):
    """Mutating what a consumer returns must not poison the shared memo."""
    cache = tmp_path / "charts.json"
    _write(cache, {"charts": {"AAPL:1D": {"timestamp": time.time(), "rows": [{"close": 1.0}]}}})

    first = service._direct_cached_chart_data_from(cache, "AAPL", "1D", allow_stale=True)
    assert first and first[0]["close"] == 1.0
    first[0]["close"] = 999.0

    second = service._direct_cached_chart_data_from(cache, "AAPL", "1D", allow_stale=True)
    assert second[0]["close"] == 1.0, "memoised rows were mutated through a consumer"


def test_concurrent_reads_do_not_corrupt_the_memo(tmp_path):
    cache = tmp_path / "charts.json"
    _write(cache, {"charts": {f"S{i}:1D": {"rows": []} for i in range(200)}})

    seen: list[int] = []
    errors: list[BaseException] = []

    def worker():
        try:
            for _ in range(25):
                seen.append(len(service._read_json_cache(cache).get("charts", {})))
        except BaseException as exc:  # noqa: BLE001 -- surfaced by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert set(seen) == {200}


def test_memo_is_clearable_for_tests(tmp_path, counted_reads):
    cache = tmp_path / "charts.json"
    _write(cache, {"charts": {}})

    service._read_json_cache(cache)
    service._reset_json_cache()
    service._read_json_cache(cache)

    assert len(counted_reads) == 2


def test_missing_file_returns_empty_and_forgets_previous_content(tmp_path):
    cache = tmp_path / "charts.json"
    _write(cache, {"charts": {"AAPL:1D": {"rows": []}}})
    assert service._read_json_cache(cache)["charts"]

    cache.unlink()
    assert service._read_json_cache(cache) == {}
