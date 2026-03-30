# =====================================================
# STOCKNEWSBR TELEGRAM BOT
# =====================================================

import asyncio
import logging
import os

import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes


TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
API_BASE_URL = os.getenv("API_BASE_URL", "").rstrip("/")
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "").strip()

REQUEST_TIMEOUT = 8
MAX_MSG = 3500

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("stocknewsbr.telegram.bot")

client = httpx.AsyncClient(
    timeout=REQUEST_TIMEOUT,
    limits=httpx.Limits(
        max_connections=20,
        max_keepalive_connections=10,
    ),
)


def _internal_headers():
    headers = {}

    if INTERNAL_API_TOKEN:
        headers["X-Internal-Token"] = INTERNAL_API_TOKEN

    return headers


async def api_get(endpoint, internal=False):
    if not API_BASE_URL:
        logger.warning("API_BASE_URL is not configured")
        return None

    url = f"{API_BASE_URL}{endpoint}"

    try:
        response = await client.get(
            url,
            headers=_internal_headers() if internal else None,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.warning("API request error on %s: %s", endpoint, exc)
        return None


async def api_post(endpoint, payload, internal=False):
    if not API_BASE_URL:
        logger.warning("API_BASE_URL is not configured")
        return None

    url = f"{API_BASE_URL}{endpoint}"

    try:
        response = await client.post(
            url,
            json=payload,
            headers=_internal_headers() if internal else None,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.warning("API request error on %s: %s", endpoint, exc)
        return None


async def get_telegram_access(update: Update):
    if not update.effective_user:
        return None

    telegram_id = str(update.effective_user.id)
    return await api_get(f"/internal/telegram/access/{telegram_id}", internal=True)


def access_denied_message():
    return (
        "Seu acesso ao Telegram ainda nao esta liberado.\n\n"
        "A assinatura principal do StockNewsBR acontece no app Google Play e libera:\n"
        "- app Android\n"
        "- website profissional\n"
        "- canal e bot do Telegram\n\n"
        "Entre no app, faca login na sua conta e vincule seu Telegram para continuar."
    )


async def consume_link_code(update: Update, link_code: str):
    if not update.effective_user:
        return None

    return await api_post(
        "/internal/telegram/link/consume",
        {
            "link_code": link_code,
            "telegram_id": str(update.effective_user.id),
            "telegram_username": update.effective_user.username,
        },
        internal=True,
    )


async def require_access(update: Update):
    if not update.message:
        return None

    access = await get_telegram_access(update)

    if not access or not access.get("allowed"):
        await update.message.reply_text(access_denied_message())
        return None

    return access


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if context.args:
        payload = await consume_link_code(update, context.args[0].strip().upper())

        if not payload or not payload.get("ok"):
            detail = payload.get("detail") if payload else "telegram_link_failed"
            await update.message.reply_text(
                "Nao foi possivel vincular sua conta agora.\n\n"
                f"Motivo: {detail}\n"
                "Gere um novo link seguro dentro do app ou da web e tente novamente."
            )
            return

        await update.message.reply_text(
            "Conta vinculada com sucesso.\n\n"
            f"Email: {payload.get('email')}\n"
            f"Plano: {payload.get('plan')}\n"
            "Seu Telegram agora segue a permissao central da sua conta StockNewsBR."
        )
        return

    await update.message.reply_text(
        "StockNewsBR\n\n"
        "Bot oficial de alertas e ranking.\n"
        "A assinatura do app Google libera app, website e Telegram.\n\n"
        "Comandos:\n"
        "/status\n"
        "/ranking\n"
        "/top\n"
        "/acao PETR4\n\n"
        "Para vincular com seguranca, gere um link dentro do app ou da web e abra o bot pelo link."
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    del context

    if not update.message:
        return

    access = await get_telegram_access(update)

    if not access or not access.get("linked"):
        await update.message.reply_text(access_denied_message())
        return

    text = (
        f"Plano: {access.get('plan', 'desconhecido')}\n"
        f"Status: {access.get('plan_status', 'desconhecido')}\n"
        f"Telegram liberado: {'sim' if access.get('allowed') else 'nao'}"
    )
    await update.message.reply_text(text)


async def show_opportunities(update: Update, limit: int):
    if not update.message:
        return

    access = await require_access(update)

    if not access:
        return

    data = await api_get(f"/internal/opportunities?limit={limit}", internal=True)

    if not data:
        await update.message.reply_text("API indisponivel no momento.")
        return

    signals = data.get("signals", [])

    if not signals:
        await update.message.reply_text("Nenhum sinal disponivel agora.")
        return

    lines = ["Market Signals\n"]

    for signal in signals[:limit]:
        ticker = signal.get("ticker", "?")
        score = signal.get("score", "?")
        price = signal.get("price", "?")
        lines.append(f"{ticker} | Score {score} | Preco {price}")

    message = "\n".join(lines)[:MAX_MSG]
    await update.message.reply_text(message)


async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    del context
    await show_opportunities(update, 5)


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    del context
    await show_opportunities(update, 10)


async def acao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    access = await require_access(update)

    if not access:
        return

    if not context.args:
        await update.message.reply_text("Use: /acao PETR4")
        return

    ticker = context.args[0].upper()
    data = await api_get("/internal/opportunities?limit=50", internal=True)

    if not data:
        await update.message.reply_text("API indisponivel.")
        return

    for signal in data.get("signals", []):
        symbol = str(signal.get("ticker", "")).upper()

        if ticker == symbol:
            message = (
                f"{symbol}\n"
                f"Score: {signal.get('score', '?')}\n"
                f"Preco: {signal.get('price', '?')}\n"
                f"Sinal: {signal.get('signal', 'indefinido')}"
            )
            await update.message.reply_text(message)
            return

    await update.message.reply_text("Ativo nao encontrado nos sinais atuais.")


async def shutdown():
    try:
        await client.aclose()
    except Exception:
        pass


def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN nao configurado")

    logger.info("Iniciando Telegram Bot")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("ranking", ranking))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("acao", acao))

    logger.info("Bot rodando")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            asyncio.run(shutdown())
        except RuntimeError:
            pass
