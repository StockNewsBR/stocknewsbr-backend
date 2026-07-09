import base64
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.testclient import TestClient

TEST_SECRET_KEY = "mission31b0-jwt-key-valid-20260630-x9"
os.environ["SECRET_KEY"] = TEST_SECRET_KEY

from app import security
from app.core import settings as runtime_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
_SECRET_MISSING = object()


def _unsigned_jwt(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}
    parts = []
    for item in (header, payload):
        raw = json.dumps(item, separators=(",", ":")).encode("utf-8")
        parts.append(base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii"))
    return ".".join(parts) + "."


def _jwt_secret() -> str:
    return security.get_jwt_secret()


def _run_python_with_secret(
    code: str,
    secret=_SECRET_MISSING,
    env_value="production",
    cwd=REPO_ROOT,
    pythonpath_entries=(),
):
    env = os.environ.copy()
    pythonpath = os.pathsep.join([*(str(path) for path in pythonpath_entries), str(REPO_ROOT)])
    env.update(
        {
            "PYTHONPATH": pythonpath,
            "DATABASE_URL": "sqlite:///:memory:",
            "START_ENGINE_WORKER": "false",
            "START_REFERRAL_WORKER": "false",
            "START_SNAPSHOT_WORKER": "false",
            "START_AI_WORKER": "false",
            "START_QUOTE_WARMUP": "false",
        }
    )

    if env_value is _SECRET_MISSING:
        env.pop("ENV", None)
    else:
        env["ENV"] = env_value

    if secret is _SECRET_MISSING:
        env.pop("SECRET_KEY", None)
    else:
        env["SECRET_KEY"] = secret

    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


class _FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.result


class _FakeDb:
    def __init__(self, user, session=None):
        self.user = user
        self.session = session
        self.added = []

    def query(self, model):
        if model is security.User:
            return _FakeQuery(self.user)
        if model is security.UserSession:
            return _FakeQuery(self.session)
        return _FakeQuery(None)

    def add(self, item):
        self.added.append(item)


class JwtCompatibilityTests(unittest.TestCase):
    def assert_secret_failure_is_sanitized(self, result, rejected_value=None):
        output = f"{result.stdout}\n{result.stderr}"

        self.assertNotEqual(result.returncode, 0, output)
        self.assertIn("SECRET_KEY", output)
        if rejected_value:
            self.assertNotIn(rejected_value, output)

    def test_missing_empty_space_and_placeholder_secret_keys_fail_closed(self):
        cases = (
            ("missing", _SECRET_MISSING, None),
            ("empty", "", None),
            ("spaces", "   ", None),
            ("old_public_placeholder", "CHANGE_THIS_SECRET", "CHANGE_THIS_SECRET"),
            ("settings_placeholder", "change_this_in_production", "change_this_in_production"),
            (
                "env_example_placeholder",
                "<defina-uma-chave-forte-fora-do-repositorio>",
                "<defina-uma-chave-forte-fora-do-repositorio>",
            ),
            ("too_short", "short-but-random-looking", "short-but-random-looking"),
            ("trivial_repeated_password", "passwordpasswordpasswordpassword", None),
            ("single_character_repeated", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", None),
        )

        for label, secret, rejected_value in cases:
            with self.subTest(label=label):
                result = _run_python_with_secret(
                    """
                    from app import security

                    security.create_access_token({"sub": 1})
                    """,
                    secret=secret,
                )

                self.assert_secret_failure_is_sanitized(result, rejected_value)

    def test_dotenv_load_happens_before_final_env_and_secret_reads(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "dotenv.py").write_text(
                "\n".join(
                    [
                        "import os",
                        "def load_dotenv():",
                        "    os.environ['ENV'] = 'production'",
                        f"    os.environ['SECRET_KEY'] = {TEST_SECRET_KEY!r}",
                        "    return True",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = _run_python_with_secret(
                """
                from app.core.settings import settings

                print(settings.ENV)
                print(settings.DEBUG)
                print(settings.SECRET_KEY)
                """,
                secret=_SECRET_MISSING,
                env_value=_SECRET_MISSING,
                pythonpath_entries=(tmp_dir,),
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines(), ["production", "False", TEST_SECRET_KEY])

    def test_production_process_env_skips_dotenv_loading(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "dotenv.py").write_text(
                "\n".join(
                    [
                        "def load_dotenv():",
                        "    raise RuntimeError('DOTENV_SHOULD_NOT_LOAD')",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = _run_python_with_secret(
                """
                from app.core.settings import validate_runtime_security_settings

                validate_runtime_security_settings()
                """,
                secret=_SECRET_MISSING,
                env_value="production",
                pythonpath_entries=(tmp_dir,),
            )

        self.assert_secret_failure_is_sanitized(result)
        self.assertNotIn("DOTENV_SHOULD_NOT_LOAD", result.stdout + result.stderr)

    def test_create_access_token_without_secret_fails_before_signing(self):
        result = _run_python_with_secret(
            """
            from app import security

            token = security.create_access_token({"sub": 1})
            print(token)
            """
        )

        self.assert_secret_failure_is_sanitized(result)
        self.assertNotIn("eyJ", result.stdout)

    def test_decode_access_token_without_secret_fails_before_identity(self):
        result = _run_python_with_secret(
            """
            from app import security

            security.decode_access_token_payload("not-a-jwt")
            """
        )

        self.assert_secret_failure_is_sanitized(result)

    def test_settings_secret_property_uses_validated_source(self):
        self.assertEqual(runtime_settings.settings.SECRET_KEY, TEST_SECRET_KEY)

        result = _run_python_with_secret(
            """
            from app.core.settings import settings

            print(settings.SECRET_KEY)
            """,
            secret="CHANGE_THIS_SECRET",
        )

        self.assert_secret_failure_is_sanitized(result, "CHANGE_THIS_SECRET")

    def test_fastapi_startup_fails_without_secret_and_passes_with_explicit_secret(self):
        missing_secret = _run_python_with_secret(
            """
            from fastapi.testclient import TestClient
            from main import app

            with TestClient(app) as client:
                print(client.get("/ping").status_code)
            """
        )
        self.assert_secret_failure_is_sanitized(missing_secret)
        self.assertNotIn("CHANGE_THIS_SECRET", missing_secret.stdout + missing_secret.stderr)

        explicit_secret = _run_python_with_secret(
            """
            from fastapi.testclient import TestClient
            from main import app

            with TestClient(app) as client:
                print(client.get("/ping").status_code)
            """,
            secret=TEST_SECRET_KEY,
        )

        self.assertEqual(explicit_secret.returncode, 0, explicit_secret.stderr)
        self.assertIn("200", explicit_secret.stdout)

    def test_valid_token_normalizes_jwt_sub_and_preserves_public_payload(self):
        for subject in (0, "0", 123, "123"):
            with self.subTest(subject=subject):
                token = security.create_access_token({"sub": subject, "sid": "session-web-1"})

                raw_payload = security.jwt.decode(
                    token,
                    _jwt_secret(),
                    algorithms=[security.ALGORITHM],
                )
                payload = security.decode_access_token_payload(token)

                self.assertEqual(raw_payload["sub"], str(int(subject)))
                self.assertEqual(payload["sub"], int(subject))
                self.assertEqual(payload["sid"], "session-web-1")
                self.assertEqual(payload.get("iat").__class__, int)
                self.assertEqual(payload.get("exp").__class__, int)

    def test_expired_token_is_rejected(self):
        token = security.jwt.encode(
            {"sub": "123", "exp": datetime.utcnow() - timedelta(minutes=1)},
            _jwt_secret(),
            algorithm=security.ALGORITHM,
        )

        with self.assertRaises(Exception) as context:
            security.decode_access_token_payload(token)

        self.assertEqual(getattr(context.exception, "status_code", None), 401)

    def test_invalid_signature_is_rejected(self):
        token = security.jwt.encode(
            {"sub": "123", "exp": datetime.utcnow() + timedelta(minutes=5)},
            "wrong-secret",
            algorithm=security.ALGORITHM,
        )

        with self.assertRaises(Exception) as context:
            security.decode_access_token_payload(token)

        self.assertEqual(getattr(context.exception, "status_code", None), 401)

    def test_old_public_secret_key_is_rejected_when_explicit_secret_is_configured(self):
        token = security.jwt.encode(
            {"sub": "123", "exp": datetime.utcnow() + timedelta(minutes=5)},
            "CHANGE_THIS_SECRET",
            algorithm=security.ALGORITHM,
        )

        with self.assertRaises(Exception) as context:
            security.decode_access_token_payload(token)

        self.assertEqual(getattr(context.exception, "status_code", None), 401)

    def test_missing_subject_is_rejected(self):
        token = security.jwt.encode(
            {"exp": datetime.utcnow() + timedelta(minutes=5)},
            _jwt_secret(),
            algorithm=security.ALGORITHM,
        )

        with self.assertRaises(Exception) as context:
            security.decode_access_token_payload(token)

        self.assertEqual(getattr(context.exception, "status_code", None), 401)

    def test_create_access_token_rejects_null_subject(self):
        with self.assertRaises(ValueError):
            security.create_access_token({"sub": None, "sid": "session-web-1"})

    def test_create_access_token_rejects_missing_subject(self):
        with self.assertRaises(ValueError):
            security.create_access_token({"sid": "session-web-1"})

    def test_null_subject_in_signed_token_is_rejected(self):
        token = security.jwt.encode(
            {
                "sub": None,
                "exp": datetime.utcnow() + timedelta(minutes=5),
            },
            _jwt_secret(),
            algorithm=security.ALGORITHM,
        )

        raw_payload = security.jwt.get_unverified_claims(token)

        self.assertIn("sub", raw_payload)
        self.assertIsNone(raw_payload.get("sub"))

        with self.assertRaises(Exception) as context:
            security.decode_access_token_payload(token)

        self.assertEqual(getattr(context.exception, "status_code", None), 401)

    def test_create_access_token_rejects_non_numeric_subject(self):
        for subject in ("abc", 123.4, "123.4", "00123", " 123", "+123"):
            with self.subTest(subject=subject):
                with self.assertRaises(ValueError):
                    security.create_access_token({"sub": subject, "sid": "session-web-1"})

    def test_create_access_token_rejects_boolean_subject(self):
        for subject in (True, False):
            with self.subTest(subject=subject):
                with self.assertRaises(ValueError):
                    security.create_access_token({"sub": subject, "sid": "session-web-1"})

    def test_boolean_subject_in_signed_token_is_rejected(self):
        for subject in (True, False):
            with self.subTest(subject=subject):
                token = security.jwt.encode(
                    {"sub": subject, "exp": datetime.utcnow() + timedelta(minutes=5)},
                    _jwt_secret(),
                    algorithm=security.ALGORITHM,
                )

                with self.assertRaises(Exception) as context:
                    security.decode_access_token_payload(token)

                self.assertEqual(getattr(context.exception, "status_code", None), 401)

    def test_malformed_and_none_algorithm_tokens_are_rejected(self):
        none_alg_token = _unsigned_jwt(
            {
                "sub": "123",
                "exp": int((datetime.utcnow() + timedelta(minutes=5)).timestamp()),
            }
        )
        malformed_tokens = (
            "not-a-jwt",
            none_alg_token,
            security.jwt.encode(
                {"sub": "abc", "exp": datetime.utcnow() + timedelta(minutes=5)},
                _jwt_secret(),
                algorithm=security.ALGORITHM,
            ),
            security.jwt.encode(
                {"sub": "00123", "exp": datetime.utcnow() + timedelta(minutes=5)},
                _jwt_secret(),
                algorithm=security.ALGORITHM,
            ),
            security.jwt.encode(
                {"sub": " 123", "exp": datetime.utcnow() + timedelta(minutes=5)},
                _jwt_secret(),
                algorithm=security.ALGORITHM,
            ),
            security.jwt.encode(
                {"sub": "+123", "exp": datetime.utcnow() + timedelta(minutes=5)},
                _jwt_secret(),
                algorithm=security.ALGORITHM,
            ),
        )

        for token in malformed_tokens:
            with self.subTest(token=token):
                with self.assertRaises(Exception) as context:
                    security.decode_access_token_payload(token)

                self.assertEqual(getattr(context.exception, "status_code", None), 401)

    def test_mission_31b_sid_policy_rejects_legacy_tokens_for_all_plans(self):
        # Mission 31B legacy-token policy: immediate revocation. A token
        # without sid is rejected for EVERY plan (previously only strict ones).
        token_without_sid = security.create_access_token({"sub": 123})
        free_user = SimpleNamespace(id=123, plan="free")
        premium_user = SimpleNamespace(id=123, plan="premium")

        for user in (free_user, premium_user):
            with self.subTest(plan=user.plan):
                with self.assertRaises(Exception) as context:
                    security.resolve_token_user(token_without_sid, _FakeDb(user))

                self.assertEqual(getattr(context.exception, "status_code", None), 401)

        session = SimpleNamespace(
            session_id="session-web-1",
            last_seen_at=None,
            revoked_at=None,
            revoked_reason=None,
            expires_at=None,
        )
        token_with_sid = security.create_access_token(
            {"sub": 123, "sid": "session-web-1"}
        )
        db = _FakeDb(premium_user, session=session)

        self.assertIs(security.resolve_token_user(token_with_sid, db), premium_user)
        self.assertEqual(db.added, [session])


class MultipartCompatibilityTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()

        @app.post("/multipart")
        async def multipart_endpoint(note: str = Form(...), file: UploadFile = File(...)):
            body = await file.read()
            return {
                "note": note,
                "filename": file.filename,
                "content_type": file.content_type,
                "size": len(body),
            }

        self.client = TestClient(app)

    def test_valid_multipart_form_and_upload_are_accepted(self):
        response = self.client.post(
            "/multipart",
            data={"note": "ok"},
            files={"file": ("chart.png", b"abc", "image/png")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["note"], "ok")
        self.assertEqual(response.json()["filename"], "chart.png")
        self.assertEqual(response.json()["content_type"], "image/png")
        self.assertEqual(response.json()["size"], 3)

    def test_empty_or_wrong_content_type_forms_return_4xx_not_500(self):
        empty_response = self.client.post("/multipart", data={})
        missing_boundary_response = self.client.post(
            "/multipart",
            content=b"note=ok",
            headers={"content-type": "multipart/form-data"},
        )
        wrong_type_response = self.client.post(
            "/multipart",
            content=b"note=ok",
            headers={"content-type": "text/plain"},
        )

        self.assertGreaterEqual(empty_response.status_code, 400)
        self.assertLess(empty_response.status_code, 500)
        self.assertGreaterEqual(missing_boundary_response.status_code, 400)
        self.assertLess(missing_boundary_response.status_code, 500)
        self.assertGreaterEqual(wrong_type_response.status_code, 400)
        self.assertLess(wrong_type_response.status_code, 500)

    def test_truncated_multipart_boundary_returns_4xx_not_500(self):
        response = self.client.post(
            "/multipart",
            content=(
                b"--mission31b0\r\n"
                b'Content-Disposition: form-data; name="note"\r\n\r\n'
                b"ok\r\n"
                b"--mission31b0\r\n"
                b'Content-Disposition: form-data; name="file"; filename="bad.png"\r\n'
                b"Content-Type: image/png\r\n\r\n"
                b"abc"
            ),
            headers={"content-type": "multipart/form-data; boundary=mission31b0"},
        )

        self.assertGreaterEqual(response.status_code, 400)
        self.assertLess(response.status_code, 500)


if __name__ == "__main__":
    unittest.main()
