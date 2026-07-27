import pytest
from main import _cors_origins

def test_cors_origins_empty_string(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "")
    assert _cors_origins() == []

def test_cors_origins_spaces(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "   ")
    assert _cors_origins() == []

def test_cors_origins_valid(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://example.com")
    assert _cors_origins() == ["http://example.com"]

def test_cors_origins_multiple(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://example.com, https://example.org")
    assert _cors_origins() == ["http://example.com", "https://example.org"]

def test_cors_origins_not_set(monkeypatch):
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    # Default is "https://www.stocknewsbr.com,https://stocknewsbr.com,http://localhost:3000,http://127.0.0.1:3000"
    assert _cors_origins() == [
        "https://www.stocknewsbr.com",
        "https://stocknewsbr.com",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ]
