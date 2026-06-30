import base64
import json
import unittest
from datetime import datetime, timedelta

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.testclient import TestClient

from app import security


def _unsigned_jwt(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}
    parts = []
    for item in (header, payload):
        raw = json.dumps(item, separators=(",", ":")).encode("utf-8")
        parts.append(base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii"))
    return ".".join(parts) + "."


class JwtCompatibilityTests(unittest.TestCase):
    def test_valid_token_normalizes_jwt_sub_and_preserves_public_payload(self):
        token = security.create_access_token({"sub": 123, "sid": "session-web-1"})

        raw_payload = security.jwt.decode(
            token,
            security.SECRET_KEY,
            algorithms=[security.ALGORITHM],
        )
        payload = security.decode_access_token_payload(token)

        self.assertEqual(raw_payload["sub"], "123")
        self.assertEqual(payload["sub"], 123)
        self.assertEqual(payload["sid"], "session-web-1")
        self.assertEqual(payload.get("iat").__class__, int)
        self.assertEqual(payload.get("exp").__class__, int)

    def test_expired_token_is_rejected(self):
        token = security.jwt.encode(
            {"sub": "123", "exp": datetime.utcnow() - timedelta(minutes=1)},
            security.SECRET_KEY,
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

    def test_missing_subject_is_rejected(self):
        token = security.jwt.encode(
            {"exp": datetime.utcnow() + timedelta(minutes=5)},
            security.SECRET_KEY,
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
            security.SECRET_KEY,
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
                    security.SECRET_KEY,
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
        malformed_sub_token = security.jwt.encode(
            {"sub": "abc", "exp": datetime.utcnow() + timedelta(minutes=5)},
            security.SECRET_KEY,
            algorithm=security.ALGORITHM,
        )

        for token in ("not-a-jwt", none_alg_token, malformed_sub_token):
            with self.subTest(token=token):
                with self.assertRaises(Exception) as context:
                    security.decode_access_token_payload(token)

                self.assertEqual(getattr(context.exception, "status_code", None), 401)


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
        wrong_type_response = self.client.post(
            "/multipart",
            content=b"note=ok",
            headers={"content-type": "text/plain"},
        )

        self.assertGreaterEqual(empty_response.status_code, 400)
        self.assertLess(empty_response.status_code, 500)
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
