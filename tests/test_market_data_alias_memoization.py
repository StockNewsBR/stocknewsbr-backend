"""The market-data alias expansion is recomputed dozens of times per request.

`app/services/public_market_data_service.py` carries its own `_symbol_aliases`,
separate from the one in `app/api/routes_public_market_live.py`. Measured on a
single `/public/market/bundle` call it runs **74 times for 4 distinct symbols**:
`_validated_cache_symbols` expands once per candidate, `cached_price_payloads`
expands twice more per symbol inside its fallback loop, and
`_payload_matches_symbol` / `_payload_matches_cache_key` expand again for every
payload they screen.

The expansion walks the whole alias map and rebuilds the same list every time.
It depends only on registry tables built once at import and never mutated, so
the result for a given normalized symbol is fixed.

The guard and normalization stay outside the cache: `_symbol_aliases` calls
`mark_symbol_cooldown` for invalid input, and that side effect must still fire
on every lookup. Only the expansion is memoized — the same split already used
for the routes-layer alias helper.
"""

from __future__ import annotations

import pytest

import app.services.public_market_data_service as service


@pytest.fixture(autouse=True)
def _clear_alias_cache():
    cached = getattr(service, "_symbol_aliases_cached", None)
    if cached is not None:
        cached.cache_clear()
    yield
    if cached is not None:
        cached.cache_clear()


def _count_expansions(monkeypatch) -> list[str]:
    calls: list[str] = []
    original = service.canonical_symbol_aliases

    def counting(value):
        calls.append(str(value))
        return original(value)

    monkeypatch.setattr(service, "canonical_symbol_aliases", counting)
    return calls


class TestAliasMemoization:
    def test_repeated_lookups_expand_once(self, monkeypatch):
        calls = _count_expansions(monkeypatch)

        for _ in range(26):
            service._symbol_aliases("PETR4")

        assert len(calls) == 1, f"expected one expansion, got {len(calls)}"

    def test_distinct_symbols_expand_independently(self, monkeypatch):
        calls = _count_expansions(monkeypatch)

        for _ in range(5):
            service._symbol_aliases("PETR4")
            service._symbol_aliases("VALE3")

        assert len(calls) == 2

    def test_equivalent_spellings_share_one_entry(self, monkeypatch):
        calls = _count_expansions(monkeypatch)

        service._symbol_aliases("petr4")
        service._symbol_aliases("PETR4")
        service._symbol_aliases(" PETR4 ")

        assert len(calls) == 1


class TestSideEffectsPreserved:
    def test_invalid_symbol_still_marks_a_cooldown_every_time(self, monkeypatch):
        """The cooldown is the reason normalization stays outside the cache."""
        marked: list[tuple[str, str]] = []
        monkeypatch.setattr(
            service,
            "mark_symbol_cooldown",
            lambda symbol, reason: marked.append((symbol, reason)),
        )
        monkeypatch.setattr(service, "canonical_symbol", lambda _v: "")
        monkeypatch.setattr(
            service, "sanitize_market_symbol", lambda _v, allow_provider_symbols=False: ""
        )

        service._symbol_aliases("!!!bogus")
        service._symbol_aliases("!!!bogus")

        assert marked == [("!!!bogus", "invalid_symbol"), ("!!!bogus", "invalid_symbol")]

    def test_ambiguous_crypto_symbol_returns_empty(self, monkeypatch):
        monkeypatch.setattr(service, "is_ambiguous_crypto_symbol", lambda _v: True)
        assert service._symbol_aliases("BTC") == []

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_empty_symbol_returns_empty_list(self, value):
        assert service._symbol_aliases(value) == []


class TestContractPreserved:
    def test_results_are_equal_across_calls(self):
        assert service._symbol_aliases("PETR4") == service._symbol_aliases("PETR4")

    def test_each_caller_gets_an_independent_list(self):
        first = service._symbol_aliases("PETR4")
        second = service._symbol_aliases("PETR4")

        assert first is not second, "callers must not share a cached list object"

        first.append("__MUTATED__")
        assert "__MUTATED__" not in service._symbol_aliases("PETR4")

    def test_returns_a_list_of_upper_case_strings(self):
        result = service._symbol_aliases("PETR4")

        assert isinstance(result, list)
        assert result == [value.upper().strip() for value in result]
        assert len(result) == len(set(result)), "aliases must stay deduplicated"

    def test_known_symbol_contains_itself(self):
        assert "PETR4" in service._symbol_aliases("PETR4")

    def test_b3_symbol_keeps_its_sa_form(self):
        assert "PETR4.SA" in service._symbol_aliases("PETR4")
