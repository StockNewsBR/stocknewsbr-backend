import pytest
from unittest.mock import Mock, patch

from app.services.gif_service import is_approved_gif_url, search_tenor_gifs
from app.social.guardian import SocialGuardian


def test_gif_search_is_explicitly_unavailable_without_server_key(monkeypatch):
    monkeypatch.delenv("TENOR_API_KEY", raising=False)

    payload = search_tenor_gifs("bull market")

    assert payload["status"] == "UNAVAILABLE"
    assert payload["items"] == []


def test_gif_search_keeps_only_approved_tenor_media(monkeypatch):
    monkeypatch.setenv("TENOR_API_KEY", "server-secret")
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "results": [
            {
                "id": "safe",
                "content_description": "Market reaction",
                "media_formats": {
                    "gif": {"url": "https://media.tenor.com/safe.gif", "dims": [320, 240]},
                    "tinygif": {"url": "https://media.tenor.com/safe-preview.gif"},
                },
            },
            {
                "id": "unsafe",
                "media_formats": {"gif": {"url": "https://example.com/tracker.gif"}},
            },
        ]
    }

    with patch("app.services.gif_service.httpx.get", return_value=response) as request:
        payload = search_tenor_gifs("bull market", locale="pt-BR", limit=50)

    assert payload["status"] == "READY"
    assert [item["id"] for item in payload["items"]] == ["safe"]
    assert request.call_args.kwargs["params"]["limit"] == 24
    assert request.call_args.kwargs["params"]["key"] == "server-secret"


@pytest.mark.parametrize("provider_payload", [[], "valid-json-string", None])
def test_gif_search_rejects_valid_json_with_non_object_payload(monkeypatch, provider_payload):
    monkeypatch.setenv("TENOR_API_KEY", "server-secret")
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = provider_payload

    with patch("app.services.gif_service.httpx.get", return_value=response):
        payload = search_tenor_gifs("bull market")

    assert payload == {
        "status": "ERROR",
        "query": "bull market",
        "items": [],
        "reason": "invalid_provider_payload",
    }


def test_social_guardian_allows_only_exact_https_tenor_media_host():
    safe = "https://media.tenor.com/market.gif"

    assert is_approved_gif_url(safe)
    assert SocialGuardian.validate_attachment_url(safe).allowed
    assert not is_approved_gif_url("http://media.tenor.com/market.gif")
    assert not is_approved_gif_url("https://media.tenor.com.example.org/market.gif")
    assert not SocialGuardian.validate_attachment_url("https://example.org/market.gif").allowed
