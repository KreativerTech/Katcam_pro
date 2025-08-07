import asyncio
import pytz
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.ext import JobQueue
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = '8469077425:AAHqX9VHAez2eRik25l844YsQ1bfqrESff8'  # <-- Tu token real

# Funciones del bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hola, soy tu bot Katcam funcionando en Python 3.13.")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📩 Recibido: {update.message.text}")

async def main():
    # Crear un scheduler con zona horaria pytz
    scheduler = AsyncIOScheduler(timezone=pytz.UTC)
    scheduler.start()

    # Crear JobQueue con ese scheduler
    job_queue = JobQueue()
    job_queue._scheduler = scheduler
    await job_queue.start()

    # Crear app manualmente
    app = Application(token=TOKEN, job_queue=job_queue)

    # Agregar handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    print("✅ Bot corriendo. Presiona Ctrl+C para detener.")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
