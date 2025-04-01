import os
import logging
import sys
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from moviepy.video.fx.all import resize
from PIL import Image
import tempfile

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

def handle_video(update: Update, context: CallbackContext) -> None:
    """Handle the video file sent by the user."""
    video_file = update.message.video.get_file()
    video_path = video_file.download()

    # Process video: take screenshot, add watermark, etc.
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as screenshot_file:
        screenshot_path = screenshot_file.name

    take_screenshot(video_path, screenshot_path)
    update.message.reply_photo(photo=open(screenshot_path, 'rb'))

    context.user_data['video_path'] = video_path
    context.user_data['screenshot_path'] = screenshot_path

    # Ask user for watermark options
    keyboard = [[InlineKeyboardButton(pos, callback_data=pos) for pos in WATERMARK_POSITIONS]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Choose watermark position:', reply_markup=reply_markup)

def take_screenshot(video_path: str, screenshot_path: str) -> None:
    """Take a screenshot from the video."""
    clip = VideoFileClip(video_path)
    frame = clip.get_frame(1)
    image = Image.fromarray(frame)
    image.save(screenshot_path)

def add_watermark(video_path: str, watermark_text: str, position: str, output_path: str) -> None:
    """Add watermark to the video."""
    video = VideoFileClip(video_path)
    watermark = TextClip(watermark_text, fontsize=24, color='white', bg_color='black')
    watermark = watermark.set_position(position).set_duration(video.duration)
    final = CompositeVideoClip([video, watermark])
    final.write_videofile(output_path)

def button(update: Update, context: CallbackContext) -> None:
    """Handle inline button presses."""
    query = update.callback_query
    query.answer()
    position = query.data

    # Ask for watermark text
    query.message.reply_text(f'You selected {position}. Now send me the watermark text.')

    context.user_data['position'] = position

def handle_text(update: Update, context: CallbackContext) -> None:
    """Handle text messages."""
    if 'position' in context.user_data:
        watermark_text = update.message.text
        video_path = context.user_data['video_path']
        position = context.user_data['position']
        output_path = 'watermarked_video.mp4'

        add_watermark(video_path, watermark_text, position, output_path)
        update.message.reply_video(video=open(output_path, 'rb'))

        # Clean up temporary files
        os.remove(video_path)
        os.remove(context.user_data['screenshot_path'])
        os.remove(output_path)

        del context.user_data['position']
        del context.user_data['video_path']
        del context.user_data['screenshot_path']
    else:
        update.message.reply_text('Send me a video file first.')

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
