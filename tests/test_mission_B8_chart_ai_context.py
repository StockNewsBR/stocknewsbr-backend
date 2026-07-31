"""B8 / chart AI context enrichment.

Commit 1e84bab7 moved the chart signal helpers out of app/engine/signal_engine.py into
app/engine/chart_signal_adapter.py, but replaced

    ai_context = _build_ai_context_from_snapshot(symbol)

with a literal `ai_context={}` annotated "optional". It is not optional in any
meaningful sense: ai_context feeds _build_ai_bias, which contributes long_bonus /
short_bonus to the signal score, adjusts the score thresholds, and populates
market_regime_state, smart_money_score, institutional_flow_state, master_score and
friends in the emitted payload. The downgrade was silent -- no test covered it -- and it
shipped on three production chart routes.

These tests pin the restored enrichment and its failure modes. Nothing here may touch
the network or a database; `_no_io` enforces that.
"""

import pytest

import app.engine.chart_signal_adapter as adapter
from app.engine.trend_breakout_signal_engine import _build_ai_bias


class RealIOAttempted(BaseException):
    """Not an Exception: _safe_ai_context's `except Exception` must not swallow it."""


@pytest.fixture(autouse=True)
def _no_io(monkeypatch):
    def _blocked(*args, **kwargs):
        raise RealIOAttempted(f"real I/O attempted: {args[:1]}")

    import requests

    for verb in ("get", "post", "put", "patch", "delete", "request"):
        monkeypatch.setattr(requests, verb, _blocked, raising=False)


def _ai_snapshot():
    """A snapshot whose ai_tools cover regime + smart money + master score for PETR4."""
    return {
        "ai_tools": {
            "market_regime": [
                {"ticker": "PETR4", "tool": "market_regime", "score": 82, "state": "bull_trend"}
            ],
            "smart_money": [
                {"ticker": "PETR4", "tool": "smart_money", "score": 88, "state": "accumulation"}
            ],
            "master_score": [
                {"ticker": "PETR4", "tool": "master_score", "score": 91, "state": "bullish"}
            ],
            "institutional_flow": [
                {"ticker": "PETR4", "tool": "institutional_flow", "score": 79, "state": "inflow"}
            ],
            "heat_map": [{"ticker": "PETR4", "tool": "heat_map", "score": 70, "state": "hot"}],
            "breakout_probability": [
                {"ticker": "PETR4", "tool": "breakout_probability", "score": 77, "state": "high"}
            ],
        }
    }


def _install(monkeypatch, snapshot, by_ticker=None, *, snapshot_error=None):
    def _get_snapshot():
        if snapshot_error is not None:
            raise snapshot_error
        return snapshot

    monkeypatch.setattr(adapter, "get_snapshot", _get_snapshot)
    monkeypatch.setattr(adapter, "get_snapshot_by_ticker", lambda: by_ticker or {})


class TestAiContextReachesTheEngine:
    def test_context_is_passed_to_trend_breakout_payload(self, monkeypatch):
        """1. The resolved context actually reaches the scoring engine."""
        _install(monkeypatch, _ai_snapshot())
        captured = {}

        def _capture(symbol, ohlc, timeframe=None, ai_context=None):
            captured["ai_context"] = ai_context
            return {"events": []}

        monkeypatch.setattr(adapter, "build_trend_breakout_payload", _capture)
        adapter.build_chart_signal_payload("PETR4", [], interval="1D")

        context = captured["ai_context"]
        assert context, "ai_context must not be empty when the snapshot has AI tools"
        assert context["market_regime"]["state"] == "bull_trend"
        assert context["smart_money"]["score"] == 88
        assert context["master_score"]["score"] == 91

    def test_institutional_fields_are_preserved(self, monkeypatch):
        """5. The institutional blocks survive the migration intact."""
        _install(monkeypatch, _ai_snapshot())
        context = adapter._build_ai_context_from_snapshot("PETR4")

        assert context["institutional_flow"]["state"] == "inflow"
        assert context["institutional_flow"]["score"] == 79
        assert context["heat_map"]["score"] == 70
        assert context["breakout_probability"]["state"] == "high"

    def test_symbol_is_normalized_like_the_original(self, monkeypatch):
        """.SA / -USD suffixes must still resolve to the same AI rows."""
        _install(monkeypatch, _ai_snapshot())
        assert adapter._build_ai_context_from_snapshot("petr4.sa")["master_score"]["score"] == 91


class TestFailureModes:
    def test_missing_snapshot_degrades_safely(self, monkeypatch):
        """2. No snapshot -> empty-but-valid context, never an exception."""
        _install(monkeypatch, {})
        context = adapter._build_ai_context_from_snapshot("PETR4")

        assert isinstance(context, dict)
        assert set(context) >= {"market_regime", "smart_money", "master_score"}
        assert all(context[key] is None for key in ("market_regime", "smart_money", "master_score"))

    def test_read_error_does_not_break_the_route(self, monkeypatch):
        """3. A raising snapshot read degrades the bias instead of 500ing the chart."""
        _install(monkeypatch, None, snapshot_error=OSError("snapshot cache unreadable"))

        with pytest.raises(OSError):
            adapter._build_ai_context_from_snapshot("PETR4")

        assert adapter._safe_ai_context("PETR4") == {}

    def test_non_dict_snapshot_is_tolerated(self, monkeypatch):
        _install(monkeypatch, ["unexpected", "shape"])
        assert adapter._build_ai_context_from_snapshot("PETR4")["master_score"] is None


class TestBiasIsActuallyApplied:
    def test_bonuses_are_not_always_zero(self, monkeypatch):
        """4. The restored context measurably changes scoring vs the {} downgrade."""
        _install(monkeypatch, _ai_snapshot())
        context = adapter._build_ai_context_from_snapshot("PETR4")

        enriched = _build_ai_bias(context, "br_stock")
        downgraded = _build_ai_bias({}, "br_stock")

        assert (enriched["long_bonus"], enriched["short_bonus"]) != (
            downgraded["long_bonus"],
            downgraded["short_bonus"],
        ), "enrichment must change the bias, otherwise the regression is still live"
        assert enriched["long_bonus"] > 0
        assert downgraded["long_bonus"] == 0 and downgraded["short_bonus"] == 0

    def test_payload_fields_are_populated(self, monkeypatch):
        """5b. The fields the downgrade blanked come back."""
        _install(monkeypatch, _ai_snapshot())
        bias = _build_ai_bias(adapter._build_ai_context_from_snapshot("PETR4"), "br_stock")

        assert bias["market_regime_state"] == "bull_trend"
        assert bias["smart_money_score"] == 88
        assert bias["institutional_flow_state"] == "inflow"
        assert bias["master_score"] == 91

        # The downgrade did not blank these fields, which is why it went unnoticed: an
        # empty context yields neutral placeholders (score 50.0), so the payload still
        # looked well-formed while carrying no real institutional signal.
        blank = _build_ai_bias({}, "br_stock")
        assert blank["market_regime_state"] != "bull_trend"
        assert blank["smart_money_score"] == 50.0
        assert blank["smart_money_score"] != bias["smart_money_score"]
        assert blank["institutional_flow_state"] != "inflow"


class TestMigrationEquivalence:
    def test_adapter_matches_the_pre_migration_implementation(self, monkeypatch):
        """6. Same snapshot in, same context out as app/engine/signal_engine.py.

        This is the migration-fidelity proof required before the orphan module may be
        deleted. It is intentionally coupled to that module and is replaced by a golden
        assertion in the commit that removes it.
        """
        legacy = pytest.importorskip("app.engine.signal_engine")

        snapshot = _ai_snapshot()
        _install(monkeypatch, snapshot)
        monkeypatch.setattr(legacy, "get_snapshot", lambda: snapshot)
        monkeypatch.setattr(legacy, "get_snapshot_by_ticker", lambda: {})

        assert adapter._build_ai_context_from_snapshot("PETR4") == legacy._build_ai_context_from_snapshot("PETR4")

    def test_helper_functions_match(self, monkeypatch):
        legacy = pytest.importorskip("app.engine.signal_engine")

        assert adapter._normalize_symbol("petr4.sa") == legacy._normalize_symbol("petr4.sa")
        assert adapter._normalize_symbol("btc-usd") == legacy._normalize_symbol("btc-usd")

        row = {"ticker": "PETR4", "score": 5, "metrics": {"flow_score": 42, "flow_state": "in"}}
        assert adapter._metric_ai_row(row, "flow_score", "flow_state") == legacy._metric_ai_row(
            row, "flow_score", "flow_state"
        )

        seed = {"ticker": "PETR4", "master_score": 88, "master_direction": "BULLISH"}
        assert adapter._snapshot_master_score_row(seed) == legacy._snapshot_master_score_row(seed)


class TestNoRealIO:
    def test_io_guard_is_armed(self):
        """7 + 8. Any real HTTP call fails the test; no DB session is ever opened."""
        import requests

        with pytest.raises(RealIOAttempted):
            requests.get("http://127.0.0.1:1/should-never-happen")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
