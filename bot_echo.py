import asyncio
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram.ext._jobqueue import JobQueue

TOKEN = '8469077425:AAHqX9VHAez2eRik25l844YsQ1bfqrESff8'  # <-- Pega tu token real aquí

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Soy tu bot Telegram con Python 3.13.")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Recibido: {update.message.text}")

async def main():
    # Crear manualmente el JobQueue con timezone pytz
    scheduler = AsyncIOScheduler(timezone=pytz.UTC)
    job_queue = JobQueue(scheduler=scheduler)
    await job_queue.start()

    # Construir la aplicación manualmente
    app = Application.builder().token(TOKEN).job_queue(job_queue).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    print("✅ Bot corriendo. Presiona Ctrl+C para detenerlo.")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
