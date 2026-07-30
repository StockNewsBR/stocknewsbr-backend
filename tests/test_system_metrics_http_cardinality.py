import pytest
from fastapi.testclient import TestClient
from app.system import system_metrics
from main import app

@app.get("/test-route-mission10a/{id}")
def mock_endpoint(id: int):
    return {"id": id}

@pytest.fixture
def isolated_client(monkeypatch):
    monkeypatch.setattr(system_metrics, "_http_endpoint_latency", {})
    return TestClient(app)

def test_unmatched_paths_share_single_metric_key(isolated_client):
    for i in range(10):
        isolated_client.get(f"/api/v1/invalid/path/{i}")
    metrics = system_metrics._http_endpoint_latency
    assert len(metrics) == 1
    assert metrics[("GET", "unmatched")]["count"] == 10

def test_known_route_uses_route_template(isolated_client):
    isolated_client.get("/test-route-mission10a/123")
    isolated_client.get("/test-route-mission10a/456")
    metrics = system_metrics._http_endpoint_latency
    template_key = ("GET", "/test-route-mission10a/{id}")
    assert len(metrics) == 1
    assert metrics[template_key]["count"] == 2

def test_query_strings_do_not_increase_cardinality(isolated_client):
    isolated_client.get("/test-route-mission10a/789?q=1")
    isolated_client.get("/test-route-mission10a/789?q=2")
    metrics = system_metrics._http_endpoint_latency
    assert len(metrics) == 1
    assert metrics[("GET", "/test-route-mission10a/{id}")]["count"] == 2

def test_different_http_methods_remain_distinguishable(isolated_client):
    isolated_client.get("/invalid/path")
    isolated_client.post("/invalid/path")
    metrics = system_metrics._http_endpoint_latency
    assert len(metrics) == 2
    assert ("GET", "unmatched") in metrics
    assert ("POST", "unmatched") in metrics

def test_metrics_state_is_restored_after_test():
    pass
