"""Regression: _ticker must canonicalize the B3 ".SA" suffix.

Root cause of Mission 69's empty IA tabs: strategic panels were keyed as "BBAS3"
but `normalized` rows carried "BBAS3.SA" at merge time, so apply_strategic_panels_by_ticker
never matched -> contract_coverage 0% -> /public/market/ai-tools produced 0 rows.
Keep _ticker suffix-agnostic so the panel merge (and any keying built on it) matches.
"""
from app.ai.strategic_panel import _ticker, apply_strategic_panels_by_ticker


def test_ticker_canonicalizes_brazil_suffix():
    assert _ticker({"ticker": "BBAS3"}) == "BBAS3"
    assert _ticker({"ticker": "BBAS3.SA"}) == "BBAS3"
    assert _ticker({"symbol": "petr4.sa"}) == "PETR4"
    assert _ticker({"ticker": "AAPL34.SA"}) == "AAPL34"
    assert _ticker({"ticker": "BTCUSD"}) == "BTCUSD"  # non-B3 untouched
    assert _ticker({}) == ""


def test_merge_attaches_panel_across_suffix_mismatch():
    # The exact production shape: panel keyed clean, signal row carries ".SA".
    panels = [{"ticker": "BBAS3", "strategic_panel_summary": "ok", "recommended_action": "AGUARDAR"}]
    rows = [{"ticker": "BBAS3.SA", "score": 50.0}]
    merged = apply_strategic_panels_by_ticker(rows, panels)
    assert isinstance(merged[0].get("strategic_panel"), dict), "panel must attach despite .SA suffix"


if __name__ == "__main__":
    test_ticker_canonicalizes_brazil_suffix()
    test_merge_attaches_panel_across_suffix_mismatch()
    print("OK: _ticker canonicalization + suffix-mismatch merge pass")
