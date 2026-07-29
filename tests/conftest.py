import pytest
import importlib
from unittest.mock import Mock

@pytest.fixture
def isolated_market_data_cache(monkeypatch):
    cache_module = importlib.import_module("app.cache.market_data_cache")

    provider_stub = Mock(return_value=None)

    monkeypatch.setattr(cache_module, "_cache_data", None)
    monkeypatch.setattr(cache_module, "_cache_key", tuple())
    monkeypatch.setattr(cache_module, "_provider_cooldown_until", 0.0)
    monkeypatch.setattr(cache_module, "fetch_market_data", provider_stub)

    yield provider_stub
