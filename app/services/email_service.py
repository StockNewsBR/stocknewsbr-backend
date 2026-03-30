import logging
import os
import smtplib
from email.message import EmailMessage


logger = logging.getLogger("stocknewsbr.email")

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_USE_TLS = str(os.getenv("SMTP_USE_TLS", "true")).strip().lower() in {"1", "true", "yes", "on"}
SMTP_USE_SSL = str(os.getenv("SMTP_USE_SSL", "false")).strip().lower() in {"1", "true", "yes", "on"}
EMAIL_FROM = os.getenv("EMAIL_FROM", "no-reply@stocknewsbr.com").strip() or "no-reply@stocknewsbr.com"


def email_delivery_mode() -> str:
    return "smtp" if SMTP_HOST else "log"


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
        f"Seu codigo de acesso para a conta {email} e: {code}\n\n"
        f"Plano atual: {plan}\n"
        f"Canal de acesso: {channel}\n"
        f"Validade: {expires_minutes} minutos\n\n"
        "Se voce nao tentou entrar, ignore este email.\n"
        "Conta Premium exige codigo por email para proteger o acesso."
    )

    if not SMTP_HOST:
        logger.info("OTP email fallback | to=%s | code=%s | plan=%s | channel=%s", email, code, plan, channel)
        return {"mode": "log", "delivered": False}

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = EMAIL_FROM
    message["To"] = email
    message.set_content(body)

    _send_via_smtp(message)
    logger.info("OTP email delivered | to=%s | channel=%s", email, channel)
    return {"mode": "smtp", "delivered": True}
