"""One request must read the hydration entry once, not four times.

Measured on a single `/public/market/bundle` call, `get_symbol_analysis` runs
four times with byte-identical arguments, from four independent call sites:

    resolve_symbol_context            (app/system/symbol_hydration.py)
    hydration_status                  (app/system/symbol_hydration.py)
    _public_market_bundle_impl        (app/api/routes_public_market_live.py)
    build_public_ai_tools_payload     (app/services/public_ai_tools_service.py)

Each one calls `_load()` (a stat, plus a full JSON parse whenever the file
changed) and then takes `_LOCK` to copy the entry out. Three of the four are
pure repeated work.

There is a correctness edge too. The hydration worker writes to this cache from
another thread, so the four reads are not guaranteed to agree: a worker that
settles mid-request makes the response carry a PENDING `hydration` block next to
an already-READY `ai_tools` section. Reading once and reusing that view gives
the response one internally consistent picture.

The memo is a ContextVar entered by the bundle route, so it covers exactly one
request and nothing leaks between them.
"""

from __future__ import annotations

import pytest

from app.system import symbol_hydration


@pytest.fixture
def counted_reads(monkeypatch):
    """Count reads that reach the underlying cache."""
    calls: list[tuple[str, str]] = []
    original = symbol_hydration._read_symbol_analysis

    def counting(symbol, timeframe="1D"):
        calls.append((symbol, timeframe))
        return original(symbol, timeframe)

    monkeypatch.setattr(symbol_hydration, "_read_symbol_analysis", counting)
    return calls


class TestRequestScopedMemo:
    def test_repeated_reads_hit_the_cache_once(self, counted_reads):
        with symbol_hydration.request_scoped_analysis():
            for _ in range(4):
                symbol_hydration.get_symbol_analysis("PETR4", "1D")

        assert len(counted_reads) == 1, (
            f"expected one underlying read per request, got {len(counted_reads)}"
        )

    def test_distinct_keys_are_read_independently(self, counted_reads):
        with symbol_hydration.request_scoped_analysis():
            symbol_hydration.get_symbol_analysis("PETR4", "1D")
            symbol_hydration.get_symbol_analysis("PETR4", "@5M")
            symbol_hydration.get_symbol_analysis("VALE3", "1D")
            symbol_hydration.get_symbol_analysis("PETR4", "1D")

        assert len(counted_reads) == 3

    def test_memo_is_inactive_outside_a_request(self, counted_reads):
        symbol_hydration.get_symbol_analysis("PETR4", "1D")
        symbol_hydration.get_symbol_analysis("PETR4", "1D")

        assert len(counted_reads) == 2, "reads outside a request must not be memoized"

    def test_memo_does_not_leak_between_requests(self, counted_reads):
        with symbol_hydration.request_scoped_analysis():
            symbol_hydration.get_symbol_analysis("PETR4", "1D")
        with symbol_hydration.request_scoped_analysis():
            symbol_hydration.get_symbol_analysis("PETR4", "1D")

        assert len(counted_reads) == 2

    def test_memo_is_released_even_when_the_body_raises(self, counted_reads):
        with pytest.raises(RuntimeError):
            with symbol_hydration.request_scoped_analysis():
                symbol_hydration.get_symbol_analysis("PETR4", "1D")
                raise RuntimeError("boom")

        # Back outside a request: reads must go through again.
        symbol_hydration.get_symbol_analysis("PETR4", "1D")
        assert len(counted_reads) == 2


class TestContractPreserved:
    def test_callers_get_independent_dicts(self):
        with symbol_hydration.request_scoped_analysis():
            first = symbol_hydration.get_symbol_analysis("PETR4", "1D")
            second = symbol_hydration.get_symbol_analysis("PETR4", "1D")

            assert first is not second, "callers must not share the memoized dict"

            first["__mutated__"] = True
            third = symbol_hydration.get_symbol_analysis("PETR4", "1D")
            assert "__mutated__" not in third

    def test_returns_a_dict_for_an_unknown_symbol(self):
        with symbol_hydration.request_scoped_analysis():
            result = symbol_hydration.get_symbol_analysis("ZZZZ9", "1D")

        assert isinstance(result, dict)

    def test_memoized_value_matches_the_direct_read(self):
        direct = symbol_hydration._read_symbol_analysis("PETR4", "1D")

        with symbol_hydration.request_scoped_analysis():
            memoized = symbol_hydration.get_symbol_analysis("PETR4", "1D")

        assert memoized == direct


class TestBundleUsesTheMemo:
    def test_bundle_request_reads_each_key_once(self, counted_reads, monkeypatch):
        import app.ai.conclusion_generator as conclusion
        import app.api.routes_public_market_live as routes

        monkeypatch.setattr(conclusion, "get_cached_or_schedule", lambda _data: None)

        routes.public_market_bundle(
            symbol="PETR4", interval="1D", limit=6, range_value=None,
            locale="pt-BR", candles=None, is_premium=True,
        )

        duplicates = {
            key: counted_reads.count(key)
            for key in set(counted_reads)
            if counted_reads.count(key) > 1
        }
        assert duplicates == {}, f"hydration entry read more than once: {duplicates}"
