"""Alias expansion must be computed once per symbol, not once per lookup.

``_symbol_aliases`` is a pure function of the symbol: it reads the alias map and
the US-exchange table, both built once at import and never mutated. Despite that
it was recomputed on every call — and a single ``/public/market/bundle`` request
calls it 14 times for the same ticker (measured), because quote resolution,
chart loading, the RVOL series and the metrics contract each expand aliases
independently.

Each expansion walks the whole alias map and runs several regexes per candidate,
so this was pure repeated work on the hottest public endpoint.

These tests pin both halves of the contract: memoize the computation, but keep
handing every caller its own mutable list.
"""

from __future__ import annotations

import pytest

import app.api.routes_public_market_live as routes


@pytest.fixture(autouse=True)
def _clear_alias_cache():
    cached = getattr(routes, "_symbol_aliases_cached", None)
    if cached is not None:
        cached.cache_clear()
    yield
    if cached is not None:
        cached.cache_clear()


def _count_expansions(monkeypatch) -> list[str]:
    """Record every call that reaches the expensive registry expansion."""
    calls: list[str] = []
    original = routes.canonical_symbol_aliases

    def counting(value):
        calls.append(str(value))
        return original(value)

    monkeypatch.setattr(routes, "canonical_symbol_aliases", counting)
    return calls


class TestAliasMemoization:
    def test_repeated_lookups_expand_once(self, monkeypatch):
        calls = _count_expansions(monkeypatch)

        for _ in range(14):
            routes._symbol_aliases("PETR4")

        assert len(calls) == 1, (
            f"expected one expansion for a repeated symbol, got {len(calls)}"
        )

    def test_distinct_symbols_expand_independently(self, monkeypatch):
        calls = _count_expansions(monkeypatch)

        routes._symbol_aliases("PETR4")
        routes._symbol_aliases("VALE3")
        routes._symbol_aliases("PETR4")
        routes._symbol_aliases("VALE3")

        assert len(calls) == 2

    def test_memoization_survives_equivalent_spellings(self, monkeypatch):
        """Normalization happens before the cache, so spellings share an entry."""
        calls = _count_expansions(monkeypatch)

        routes._symbol_aliases("petr4")
        routes._symbol_aliases("PETR4")
        routes._symbol_aliases(" PETR4 ")

        assert len(calls) == 1


class TestAliasContractPreserved:
    def test_results_are_equal_across_calls(self):
        assert routes._symbol_aliases("PETR4") == routes._symbol_aliases("PETR4")

    def test_each_caller_gets_an_independent_list(self):
        first = routes._symbol_aliases("PETR4")
        second = routes._symbol_aliases("PETR4")

        assert first is not second, "callers must not share a cached list object"

        first.append("__MUTATED__")
        assert "__MUTATED__" not in routes._symbol_aliases("PETR4"), (
            "mutating a returned list must never corrupt the cache"
        )

    def test_returns_a_plain_list(self):
        result = routes._symbol_aliases("PETR4")
        assert isinstance(result, list)
        assert all(isinstance(item, str) for item in result)

    def test_unknown_symbol_still_returns_aliases(self):
        assert isinstance(routes._symbol_aliases("ZZZZ9"), list)

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_empty_symbol_returns_empty_list(self, value):
        assert routes._symbol_aliases(value) == []

    def test_known_symbol_contains_itself(self):
        assert "PETR4" in routes._symbol_aliases("PETR4")
