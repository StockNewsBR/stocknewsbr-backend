"""One bundle request must load each chart series at most once.

``public_market_bundle`` builds its response from two helpers that each resolve
their own candles: ``public_market_insight`` loads ``(ticker, chart_interval)``
and ``public_market_chart`` loads exactly the same pair moments later. Measured
on a default ``interval=1D`` request, ``load_public_chart_rows("1D")`` ran twice
— two full alias walks and two cache reads for a series already in memory.

The fix scopes a memo to the bundle call itself (a ContextVar set on entry and
reset on exit), so duplicates inside one request collapse while nothing is
retained between requests. These tests pin both properties.
"""

from __future__ import annotations

from collections import Counter

import pytest

import app.api.routes_public_market_live as routes


@pytest.fixture(autouse=True)
def _no_llm_conclusion(monkeypatch):
    """Keep the optional LLM layer out of the request path for these tests."""
    import app.ai.conclusion_generator as conclusion

    monkeypatch.setattr(conclusion, "get_cached_or_schedule", lambda _data: None)


def _count_chart_loads(monkeypatch) -> list[str]:
    loads: list[str] = []
    original = routes.load_public_chart_rows

    def counting(aliases, interval, scope="public_market_live"):
        loads.append(str(interval))
        return original(aliases, interval, scope=scope)

    monkeypatch.setattr(routes, "load_public_chart_rows", counting)
    return loads


def _bundle(**overrides):
    params = {
        "symbol": "PETR4",
        "interval": "1D",
        "limit": 6,
        "range_value": None,
        "locale": "pt-BR",
        "candles": None,
        "is_premium": True,
    }
    params.update(overrides)
    return routes.public_market_bundle(**params)


class TestBundleChartDeduplication:
    def test_default_interval_loads_each_series_once(self, monkeypatch):
        loads = _count_chart_loads(monkeypatch)

        _bundle()

        duplicates = {key: n for key, n in Counter(loads).items() if n > 1}
        assert duplicates == {}, f"chart series loaded more than once: {duplicates}"

    def test_daily_candle_request_loads_each_series_once(self, monkeypatch):
        """candles=1d makes the chart interval equal the daily series key."""
        loads = _count_chart_loads(monkeypatch)

        _bundle(candles="1d")

        duplicates = {key: n for key, n in Counter(loads).items() if n > 1}
        assert duplicates == {}, f"chart series loaded more than once: {duplicates}"

    def test_memo_does_not_leak_between_requests(self, monkeypatch):
        """A second request must re-read, never serve the first request's rows."""
        loads = _count_chart_loads(monkeypatch)

        _bundle()
        first_count = len(loads)
        assert first_count > 0

        _bundle()
        assert len(loads) > first_count, "second request reused a stale memo"


class TestBundleStillCorrect:
    def test_bundle_payload_keeps_its_contract(self):
        payload = _bundle()

        for key in ("symbol", "quote", "insight", "chart", "news", "ai_tools",
                    "market_metrics", "data_status", "hydration", "source"):
            assert key in payload, f"missing bundle key: {key}"

    def test_chart_section_matches_a_standalone_chart_call(self):
        bundled = _bundle()["chart"]
        standalone = routes.public_market_chart("PETR4", interval="1D", range_value=None)

        assert bundled.get("ticker") == standalone.get("ticker")
        assert bundled.get("interval") == standalone.get("interval")
        assert len(bundled.get("ohlc") or []) == len(standalone.get("ohlc") or [])

    def test_memo_is_inactive_outside_a_bundle_request(self, monkeypatch):
        """Direct helper calls must not be silently memoized."""
        loads = _count_chart_loads(monkeypatch)

        routes._load_chart_data_fast("PETR4", "1D")
        routes._load_chart_data_fast("PETR4", "1D")

        assert loads.count("1D") == 2
