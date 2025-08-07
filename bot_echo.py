from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

# Reemplaza con tu TOKEN de BotFather
TOKEN = '8469077425:AAHqX9VHAez2eRik25l844YsQ1bfqrESff8'

# Función para iniciar
def start(update, context):
    update.message.reply_text("¡Hola! Soy Katcam. Envíame un mensaje y te responderé.")

# Función para responder mensajes
def echo(update, context):
    mensaje = update.message.text
    update.message.reply_text(f"Recibido: {mensaje}")

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Comando /start
    dp.add_handler(CommandHandler("start", start))

    # Responder todos los textos
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

    # Iniciar el bot
    updater.start_polling()
    print("Bot iniciado. Presiona Ctrl+C para detenerlo.")
    updater.idle()

if __name__ == '__main__':
    main()
