"""P3-B health/readiness contract regression guard.

Establishes and locks the post-H8 health contracts so infra and security
expectations stay auditable:

- `/ping` is the public liveness endpoint used by the deploy platform
  (render.yaml healthCheckPath). It must answer 200 without any auth and
  must never leak secrets or internal credentials.
- `/system/health` is the protected aggregate health surface guarded by
  `X-Internal-Token`. Without a configured token it returns 503
  `internal_token_not_configured`; without a supplied header it returns
  403 `internal_access_required`; with a valid token it returns the rich
  operational payload and must not leak secrets.
- `/system/readiness` is the protected readiness surface guarded by the
  same mechanism; without a supplied header it returns 403.
- Neither protected surface exposes credentials, secrets, tokens or
  environment values in the response body.
"""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

VALID_INTERNAL_TOKEN = "h10-health-contract-token-2026-08-04-007-42"


def _stub_snapshot_info():
    return {
        "signals": 1,
        "timestamp": 1713866400.0,
        "age_seconds": 12,
        "has_signals": True,
        "is_empty": False,
        "source": "engine",
        "stale": False,
        "snapshot_runtime_status": "OK",
        "snapshot_runtime": {"status": "OK", "signals": 1, "source": "engine"},
        "fallback_active": False,
        "last_good_signals": 1,
        "last_good_timestamp": 1713866400.0,
    }


def _stub_snapshot():
    return {"signals": [{}], "timestamp": 1713866400.0}


def _stub_go_live(*args, **kwargs):
    return {
        "go_live_ready": True,
        "institutional_consistency_score": 95.0,
        "contract_coverage": {"total": 1, "complete": 1, "missing": 0, "coverage_pct": 100.0},
        "institutional_certified": True,
        "certification_reasons": [],
    }


def _stub_paper_trading():
    return {
        "mode": "PAPER_ONLY",
        "simulation": "SIMULATED",
        "paper_trading_enabled": True,
        "paper_trading_status": "IDLE",
        "total_trades": 0,
    }


def _stub_ai_worker():
    return {"status": "idle", "snapshot_health": {"source": "engine", "cooldown_remaining_seconds": 0}}


def _stub_ai_tabs():
    return {"overall_status": "ok", "release_decision": {"go_live": True}, "batch_summary": {"approved_tools": 1}}


def _stub_polls():
    return {"polls": 1, "symbols": 1, "current_week_polls": 1, "week_key": "2026-W32"}


def _stub_metrics():
    return {"institutional_metrics": {}, "cache_age": 0, "workers": {}}


def _stub_storage():
    return {"ready": True}


def _stub_media():
    return {"cdn_ready": True}


def _stub_push():
    return {"android_ready": True, "apple_ready": True}


def _stub_moderation():
    return {}


_SECRET_WORDS = (
    "secret",
    "password",
    "token",
    "api_key",
    "apikey",
    "internal_api_token",
    "credential",
)


def _contains_secret_like(value):
    if value is None:
        return False
    text = str(value).lower()
    return any(word in text for word in _SECRET_WORDS) and any(
        sep in text for sep in (":", "=")
    )


class HealthContractTests(unittest.TestCase):
    def setUp(self):
        from app.dependencies import INTERNAL_API_TOKEN as _current
        self._original_token = _current

    def tearDown(self):
        import app.dependencies as deps
        deps.INTERNAL_API_TOKEN = self._original_token

    @patch("app.api.routes_system.get_ai_worker_report", _stub_ai_worker)
    @patch("app.api.routes_system.get_ai_tab_audit_report", _stub_ai_tabs)
    @patch("app.api.routes_system.get_snapshot_info", _stub_snapshot_info)
    @patch("app.api.routes_system.get_snapshot", _stub_snapshot)
    @patch("app.api.routes_system.get_poll_store_summary", _stub_polls)
    @patch("app.api.routes_system.get_metrics_snapshot", _stub_metrics)
    @patch("app.api.routes_system.build_go_live_status", _stub_go_live)
    @patch("app.api.routes_system._paper_trading_observability", _stub_paper_trading)
    def _client_with_token(self, token=VALID_INTERNAL_TOKEN):
        import app.dependencies as deps
        deps.INTERNAL_API_TOKEN = token
        from app.main import app
        return TestClient(app)

    def test_ping_is_public_liveness_without_auth(self):
        from app.main import app
        client = TestClient(app)
        response = client.get("/ping")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body.get("ping"), "pong")
        self.assertIn("status", body)
        self.assertIn(body["status"], ("ok", "degraded"))
        self.assertIsInstance(body.get("routers_missing"), list)
        self.assertNotIn("secret", str(body).lower())
        self.assertNotIn("token", str(body).lower())

    def test_system_health_without_configured_token_returns_503(self):
        import app.dependencies as deps
        deps.INTERNAL_API_TOKEN = ""
        from app.main import app
        client = TestClient(app)
        response = client.get("/system/health")
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json().get("detail"), "internal_token_not_configured")

    def test_system_health_without_supplied_header_returns_403(self):
        client = self._client_with_token()
        response = client.get("/system/health")
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json().get("detail"), "internal_access_required")

    def test_system_health_with_invalid_header_returns_403(self):
        client = self._client_with_token()
        response = client.get("/system/health", headers={"X-Internal-Token": "wrong-token"})
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json().get("detail"), "internal_access_required")

    def test_system_health_with_valid_token_returns_200_without_secrets(self):
        client = self._client_with_token()
        response = client.get(
            "/system/health", headers={"X-Internal-Token": VALID_INTERNAL_TOKEN}
        )
        self.assertEqual(response.status_code, 200, response.text)
        body_text = response.text.lower()
        self.assertNotIn(VALID_INTERNAL_TOKEN.lower(), body_text)
        for word in ("secret", "password", "credential"):
            self.assertNotIn(word, body_text, f"leak of '{word}' in /system/health body")

    def test_system_readiness_without_supplied_header_returns_403(self):
        client = self._client_with_token()
        response = client.get("/system/readiness")
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json().get("detail"), "internal_access_required")

    @patch("app.api.routes_system.get_metrics_snapshot", _stub_metrics)
    @patch("app.api.routes_system.get_snapshot_info", _stub_snapshot_info)
    @patch("app.api.routes_system.get_snapshot", _stub_snapshot)
    @patch("app.api.routes_system.get_storage_status", _stub_storage)
    @patch("app.api.routes_system.get_media_status", _stub_media)
    @patch("app.api.routes_system.get_push_status", _stub_push)
    @patch("app.api.routes_system.build_go_live_status", _stub_go_live)
    @patch("app.api.routes_system._paper_trading_observability", _stub_paper_trading)
    @patch("app.api.routes_system.get_moderation_summary", _stub_moderation)
    @patch("app.api.routes_system.evaluate_snapshot_runtime_status", lambda info: info.get("snapshot_runtime"))
    def test_system_readiness_with_valid_token_returns_200_without_secrets(self):
        client = self._client_with_token()
        response = client.get(
            "/system/readiness", headers={"X-Internal-Token": VALID_INTERNAL_TOKEN}
        )
        self.assertEqual(response.status_code, 200, response.text)
        body_text = response.text.lower()
        self.assertNotIn(VALID_INTERNAL_TOKEN.lower(), body_text)
        for word in ("secret", "password", "credential"):
            self.assertNotIn(word, body_text, f"leak of '{word}' in /system/readiness body")

    def test_health_contract_endpoint_paths_are_stable(self):
        from app.main import app
        spec = app.openapi()
        paths = set(spec["paths"].keys())
        self.assertIn("/ping", paths)
        self.assertIn("/system/health", paths)
        self.assertIn("/system/readiness", paths)
        self.assertNotIn("/system-health", paths, "legacy stub path must remain removed")


if __name__ == "__main__":
    unittest.main()
