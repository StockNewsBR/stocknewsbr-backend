import json
import logging
import os
import smtplib
import threading
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from app.core.settings import auth_email_test_mailbox_path


logger = logging.getLogger("stocknewsbr.email")

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_USE_TLS = str(os.getenv("SMTP_USE_TLS", "true")).strip().lower() in {"1", "true", "yes", "on"}
SMTP_USE_SSL = str(os.getenv("SMTP_USE_SSL", "false")).strip().lower() in {"1", "true", "yes", "on"}
EMAIL_FROM = os.getenv("EMAIL_FROM", "no-reply@stocknewsbr.com").strip() or "no-reply@stocknewsbr.com"

# Test-only injectable delivery override. Unit tests set this to capture
# outgoing messages in memory; it must never be set in production code paths.
_delivery_override = None
_test_mailbox_lock = threading.Lock()


def set_delivery_override(handler) -> None:
    global _delivery_override
    _delivery_override = handler


def _environment() -> str:
    return str(os.getenv("ENV", "development")).strip().lower()


def _mask_email(email: str) -> str:
    value = str(email or "").strip().lower()

    if "@" not in value:
        return "***"

    local, _, domain = value.partition("@")
    return f"{(local[0] + '***') if local else '***'}@{domain}"


def email_delivery_mode() -> str:
    if _delivery_override is not None:
        return "override"

    if SMTP_HOST:
        return "smtp"

    if auth_email_test_mailbox_path() and _environment() != "production":
        return "test_mailbox"

    return "log"


def _send_via_smtp(message: EmailMessage):
    if SMTP_USE_SSL:
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15)
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)

    with server:
        if SMTP_USE_TLS and not SMTP_USE_SSL:
            server.starttls()

        if SMTP_USERNAME:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)

        server.send_message(message)


def _append_to_test_mailbox(payload: dict) -> None:
    if _environment() == "production":
        raise RuntimeError("AUTH_EMAIL_TEST_MAILBOX_FORBIDDEN_IN_PRODUCTION")

    mailbox = Path(auth_email_test_mailbox_path())
    mailbox.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    with _test_mailbox_lock:
        with mailbox.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _deliver(email: str, subject: str, body: str, *, kind: str, metadata: dict | None = None) -> dict:
    """Delivers an e-mail through the configured provider.

    Returns {"mode": str, "delivered": bool}. The message body may contain a
    login code; therefore NOTHING from the body is ever logged.
    """
    mode = email_delivery_mode()

    if mode == "override":
        result = _delivery_override(
            {
                "to": email,
                "subject": subject,
                "body": body,
                "kind": kind,
                "metadata": dict(metadata or {}),
            }
        )
        delivered = True if result is None else bool(result)
        return {"mode": "override", "delivered": delivered}

    if mode == "smtp":
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = EMAIL_FROM
        message["To"] = email
        message.set_content(body)
        _send_via_smtp(message)
        logger.info("Email delivered | kind=%s | to=%s", kind, _mask_email(email))
        return {"mode": "smtp", "delivered": True}

    if mode == "test_mailbox":
        _append_to_test_mailbox(
            {
                "to": email,
                "subject": subject,
                "body": body,
                "kind": kind,
                "metadata": dict(metadata or {}),
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        logger.info("Email captured by test mailbox | kind=%s | to=%s", kind, _mask_email(email))
        return {"mode": "test_mailbox", "delivered": True}

    # "log" mode: no provider configured. The message is NOT delivered and the
    # code is NOT logged (Mission 31B: OTP must never reach logs).
    logger.warning(
        "Email provider not configured; message dropped | kind=%s | to=%s",
        kind,
        _mask_email(email),
    )
    return {"mode": "log", "delivered": False}


def send_login_code_email(
    email: str,
    code: str,
    plan: str,
    channel: str,
    expires_minutes: int,
):
    subject = "StockNewsBR | Codigo de acesso"
    body = (
        "StockNewsBR - Inteligencia de Mercado com IA\n\n"
        f"Seu codigo de acesso e: {code}\n\n"
        f"Validade: {expires_minutes} minutos\n\n"
        "Se voce nao tentou entrar, ignore este email."
    )

    return _deliver(
        email,
        subject,
        body,
        kind="login_code",
        metadata={"plan": plan, "channel": channel, "code": code},
    )


def send_email_change_code_email(
    email: str,
    code: str,
    expires_minutes: int,
):
    subject = "StockNewsBR | Confirmacao de novo e-mail"
    body = (
        "StockNewsBR - Inteligencia de Mercado com IA\n\n"
        f"Seu codigo para confirmar o novo e-mail e: {code}\n\n"
        f"Validade: {expires_minutes} minutos\n\n"
        "Se voce nao solicitou esta alteracao, ignore este email."
    )

    return _deliver(
        email,
        subject,
        body,
        kind="email_change_code",
        metadata={"code": code},
    )


def send_email_change_notice_email(old_email: str, new_email_masked: str):
    subject = "StockNewsBR | E-mail da conta alterado"
    body = (
        "StockNewsBR - Inteligencia de Mercado com IA\n\n"
        f"O e-mail da sua conta foi alterado para {new_email_masked}.\n\n"
        "Se voce nao reconhece esta alteracao, entre em contato com o suporte imediatamente."
    )

    return _deliver(
        old_email,
        subject,
        body,
        kind="email_change_notice",
        metadata={},
    )
