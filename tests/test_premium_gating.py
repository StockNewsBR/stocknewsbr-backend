"""Regression: premium bundle fields are gated by server-side entitlement.

Mission 72 P0. The public bundle must NOT hand premium fields (strategic_panel,
master_score, ai_tools, institutional_flow) to anonymous/Básico when gating is on,
while keeping the public fields (quote, chart, news). Premium (Trial/Pro) keeps all.
Gating is behind STOCKNEWS_PREMIUM_GATING so it is off by default; these tests force it.
"""
import copy
import importlib
import os
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

def _load_module():
    os.environ["STOCKNEWS_PREMIUM_GATING"] = "1"
    import app.api.routes_public_market_live as m
    importlib.reload(m)
    return m

_SAMPLE = {
    "symbol": "PETR4",
    "quote": {"price": 42.21},
    "insight": {"strategic_panel": {"x": 1}, "master_score": 3.9, "rsi": 61},
    "ai_tools": {"tools": {"flow": [1]}},
    "news": {"count": 6},
}

def test_anonymous_gets_public_fields_but_no_premium():
    m = _load_module()
    out = m._gate_bundle_for_entitlement(copy.deepcopy(_SAMPLE), is_premium=False)
    # premium redacted
    assert out["insight"]["strategic_panel"] is None
    assert out["insight"]["master_score"] is None
    assert out["ai_tools"]["status"] == "PREMIUM_LOCKED"
    assert out["premium_locked"] is True
    # public preserved
    assert out["quote"]["price"] == 42.21
    assert out["news"]["count"] == 6
    assert out["insight"]["rsi"] == 61

def test_premium_keeps_everything():
    m = _load_module()
    out = m._gate_bundle_for_entitlement(copy.deepcopy(_SAMPLE), is_premium=True)
    assert out["insight"]["strategic_panel"] == {"x": 1}
    assert out["insight"]["master_score"] == 3.9
    assert out["ai_tools"]["tools"] == {"flow": [1]}
    assert "premium_locked" not in out

def test_direct_insight_ignores_client_premium_claim_and_redacts_anonymous():
    m = _load_module()
    insight_route = next(route for route in m.router.routes if route.path == "/public/market/insight/{symbol}")
    assert any(dependency.call is m.resolve_premium_entitlement for dependency in insight_route.dependant.dependencies)
    premium_insight = {
        "symbol": "PETR4",
        "strategic_panel": {"recommended_action": "COMPRAR"},
        "master_score": 8.2,
        "institutional_flow": {"label": "Comprador"},
    }

    with patch.object(m, "resolve_symbol_context", return_value={}), patch.object(
        m, "_snapshot_master_context", return_value=premium_insight
    ), patch.object(m, "_load_chart_data_fast", return_value=[]):
        out = m.public_market_insight("PETR4", is_premium=False)

    assert out["strategic_panel"] is None
    assert out["master_score"] is None
    assert out["institutional_flow"] is None
    assert out["premium_locked"] is True
    assert out["access_status"] == "basic"

def test_direct_insight_keeps_premium_for_server_entitlement():
    m = _load_module()
    premium_insight = {
        "symbol": "PETR4",
        "strategic_panel": {"recommended_action": "COMPRAR"},
        "master_score": 8.2,
    }

    with patch.object(m, "resolve_symbol_context", return_value={}), patch.object(
        m, "_snapshot_master_context", return_value=premium_insight
    ), patch.object(m, "_load_chart_data_fast", return_value=[]):
        out = m.public_market_insight("PETR4", is_premium=True)

    assert out["strategic_panel"]["recommended_action"] == "COMPRAR"

def test_direct_ai_tools_route_is_server_gated():
    _load_module()
    import app.api.routes_public_market as public_routes
    ai_route = next(route for route in public_routes.router.routes if route.path == "/public/market/ai-tools")
    assert any(dependency.call is public_routes.resolve_premium_entitlement for dependency in ai_route.dependant.dependencies)

    with patch.object(
        public_routes,
        "build_public_ai_tools_payload",
        return_value={"status": "READY", "tools": {"flow": [{"ticker": "PETR4"}]}},
    ):
        anonymous = public_routes.public_ai_tools(is_premium=False)
        premium = public_routes.public_ai_tools(is_premium=True)

    assert anonymous == {"tools": {}, "status": "PREMIUM_LOCKED", "locked": True}
    assert premium["tools"]["flow"][0]["ticker"] == "PETR4"

def test_gating_defaults_fail_closed():
    os.environ.pop("STOCKNEWS_PREMIUM_GATING", None)
    import app.api.routes_public_market_live as m
    importlib.reload(m)
    assert m._PREMIUM_GATING_ENABLED is True

def test_gating_off_is_noop():
    os.environ["STOCKNEWS_PREMIUM_GATING"] = "0"
    import app.api.routes_public_market_live as m
    importlib.reload(m)
    out = m._gate_bundle_for_entitlement(copy.deepcopy(_SAMPLE), is_premium=False)
    # flag off -> nothing redacted even for anonymous (live app unaffected)
    assert out["insight"]["strategic_panel"] == {"x": 1}
    assert "premium_locked" not in out

@patch('app.dependencies.resolve_token_user')
@patch('app.dependencies.refresh_user_access')
def test_resolve_premium_entitlement(mock_refresh, mock_resolve):
    from app.dependencies import resolve_premium_entitlement
    db_mock = MagicMock()
    
    # 1. Trial user
    mock_user = MagicMock()
    mock_user.plan = 'trial'
    mock_resolve.return_value = mock_user
    assert resolve_premium_entitlement("valid_token", db_mock) is True
    
    # 2. Pro user
    mock_user.plan = 'premium'
    assert resolve_premium_entitlement("valid_token", db_mock) is True
    
    # 3. Enterprise user
    mock_user.plan = 'enterprise'
    assert resolve_premium_entitlement("valid_token", db_mock) is True
    
    # 4. Basico user
    mock_user.plan = 'basico'
    assert resolve_premium_entitlement("valid_token", db_mock) is False
    
    # 5. Invalid token
    mock_resolve.side_effect = HTTPException(status_code=401, detail="x")
    assert resolve_premium_entitlement("invalid", db_mock) is False
    
    # 6. Absent token
    assert resolve_premium_entitlement(None, db_mock) is False

    # 7. Trial expirado / Expired plan handled by refresh throwing or changing plan
    mock_resolve.side_effect = None
    mock_user.plan = 'trial'
    mock_resolve.return_value = mock_user
    def mock_refresh_behavior(user, **kwargs):
        user.plan = 'free'
    mock_refresh.side_effect = mock_refresh_behavior
    assert resolve_premium_entitlement("valid_token", db_mock) is False

if __name__ == "__main__":
    test_anonymous_gets_public_fields_but_no_premium()
    test_premium_keeps_everything()
    test_gating_off_is_noop()
    test_resolve_premium_entitlement()
    print("OK: premium gating anon-redacted / pro-full / flag-off-noop")
