import asyncio
import pytz
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = '8469077425:AAHqX9VHAez2eRik25l844YsQ1bfqrESff8'  # 👈 Reemplaza con tu token real

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hola, soy tu bot Katcam.")

# Mensajes normales
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📩 Recibido: {update.message.text}")

# Main
async def main():
    # Crea el ApplicationBuilder con un scheduler configurado con pytz
    scheduler = AsyncIOScheduler(timezone=pytz.UTC)
    scheduler.start()

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(lambda app: setattr(app.job_queue, "_scheduler", scheduler))
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    print("✅ Bot corriendo. Ctrl+C para detener.")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
