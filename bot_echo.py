import asyncio
import pytz
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

TOKEN = '8469077425:AAHqX9VHAez2eRik25l844YsQ1bfqrESff8'  # Reemplaza con tu token de BotFather

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Soy tu bot de Telegram.")

# Mensajes de texto
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Recibido: {update.message.text}")

# Main
async def main():
    # Forzar el uso de pytz para timezone
    app = ApplicationBuilder().token(TOKEN).timezone(pytz.UTC).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    print("Bot iniciado. Presiona Ctrl+C para detenerlo.")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
