import os
import logging
import requests
from requests.exceptions import RequestException
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# =====================================================
# CONFIG
# =====================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN não configurado!")

if not API_BASE_URL:
    raise ValueError("❌ API_BASE_URL não configurado!")

REQUEST_TIMEOUT = 10

# =====================================================
# LOGGING PROFISSIONAL
# =====================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)

logger = logging.getLogger("StockNewsBR-Bot")

# =====================================================
# UTIL
# =====================================================

def api_get(endpoint: str):
    try:
        response = requests.get(
            f"{API_BASE_URL}{endpoint}",
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        return response.json()
    except RequestException as e:
        logger.error(f"Erro API: {e}")
        return None

# =====================================================
# COMMANDS
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/start by {update.effective_user.id}")
    await update.message.reply_text(
        "🚀 StockNewsBR Institutional Bot\n\n"
        "Comandos disponíveis:\n"
        "/ranking\n"
        "/top 60\n"
        "/acao PETR4"
    )

async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/ranking by {update.effective_user.id}")

    data = api_get("/ranking")
    if not data:
        await update.message.reply_text("⚠️ API indisponível no momento.")
        return

    ranking_data = data.get("data", [])[:5]

    if not ranking_data:
        await update.message.reply_text("Nenhum dado disponível.")
        return

    message = "📊 TOP 5 Ranking\n\n"

    for item in ranking_data:
        message += (
            f"{item['symbol']} | "
            f"Score: {item['score']} | "
            f"{item['trend']}\n"
        )

    await update.message.reply_text(message)

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/top by {update.effective_user.id}")

    try:
        min_score = int(context.args[0]) if context.args else 50
    except ValueError:
        await update.message.reply_text("Use número válido. Ex: /top 60")
        return

    data = api_get(f"/ranking/top?min_score={min_score}")
    if not data:
        await update.message.reply_text("⚠️ API indisponível.")
        return

    ranking_data = data.get("data", [])

    if not ranking_data:
        await update.message.reply_text("Nenhum ativo encontrado.")
        return

    message = f"📈 Ativos Score ≥ {min_score}\n\n"

    for item in ranking_data[:10]:
        message += (
            f"{item['symbol']} | "
            f"{item['score']} | "
            f"{item['trend']}\n"
        )

    await update.message.reply_text(message)

async def acao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/acao by {update.effective_user.id}")

    if not context.args:
        await update.message.reply_text("Use: /acao PETR4")
        return

    ticker = context.args[0].upper() + ".SA"

    data = api_get("/ranking")
    if not data:
        await update.message.reply_text("⚠️ API indisponível.")
        return

    ranking_data = data.get("data", [])

    for item in ranking_data:
        if item["symbol"] == ticker:
            message = (
                f"📌 {item['symbol']}\n"
                f"Score: {item['score']}\n"
                f"Tendência: {item['trend']}\n"
                f"RSI: {item['rsi']}\n"
                f"Breakout: {item['breakout']}"
            )
            await update.message.reply_text(message)
            return

    await update.message.reply_text("Ativo não encontrado.")

# =====================================================
# ERROR HANDLER GLOBAL
# =====================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Erro não tratado:", exc_info=context.error)

# =====================================================
# MAIN
# =====================================================

def main():
    logger.info("🤖 Iniciando Telegram Bot...")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ranking", ranking))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("acao", acao))

    app.add_error_handler(error_handler)

    logger.info("✅ Bot rodando em modo polling...")
    app.run_polling()

if __name__ == "__main__":
    main()