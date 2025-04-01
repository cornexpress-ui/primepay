import os
import logging
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from moviepy.video.fx.all import resize
from PIL import Image
import tempfile
import sys

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define constants for watermark positions
WATERMARK_POSITIONS = ['upper-left', 'upper-right', 'lower-left', 'lower-right', 'center']

# Get the token with better error handling
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("No TELEGRAM_BOT_TOKEN environment variable found!")
    sys.exit(1)

def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    update.message.reply_text('Hi! Send me a video file to get started.')

# ... rest of the code remains the same ...

def main() -> None:
    """Start the bot."""
    try:
        logger.info("Starting bot...")
        updater = Updater(TOKEN)
        
        dispatcher = updater.dispatcher

        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(MessageHandler(Filters.video, handle_video))
        dispatcher.add_handler(CallbackQueryHandler(button))
        dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

        logger.info("Bot started successfully!")
        updater.start_polling()
        updater.idle()
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
