import os
import logging
import sys
import time
import json
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, ImageClip
from moviepy.video.fx.all import resize
from PIL import Image
import tempfile
import threading

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define constants for watermark positions
WATERMARK_POSITIONS = ['upper-left', 'upper-right', 'lower-left', 'lower-right', 'center']
WATERMARK_TYPES = ['text', 'image']
WATERMARK_OPACITY = ['25%', '50%', '75%', '100%']

# File to store user preferences
USER_PREFS_FILE = "user_preferences.json"

# Get the token with better error handling
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("No TELEGRAM_BOT_TOKEN environment variable found!")
    sys.exit(1)

def load_user_preferences():
    """Load user preferences from file"""
    if os.path.exists(USER_PREFS_FILE):
        try:
            with open(USER_PREFS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading user preferences: {e}")
    return {}

def save_user_preferences(prefs):
    """Save user preferences to file"""
    try:
        with open(USER_PREFS_FILE, 'w') as f:
            json.dump(prefs, f)
    except Exception as e:
        logger.error(f"Error saving user preferences: {e}")

# Load user preferences at startup
user_preferences = load_user_preferences()

def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    update.message.reply_text('Hi! Send me a video file to get started.')

def handle_video(update: Update, context: CallbackContext) -> None:
    """Handle the video file sent by the user."""
    user_id = str(update.effective_user.id)
    
    progress_msg = update.message.reply_text('Downloading video...')
    
    # Download video with progress updates
    video_file = update.message.video.get_file()
    video_path = video_file.download()
    
    progress_msg.edit_text('Video downloaded successfully!')
    
    # Store the video path in user_data
    context.user_data['video_path'] = video_path
    context.user_data['progress_msg'] = progress_msg
    
    # Check if user has saved preferences
    has_prefs = user_id in user_preferences and user_preferences[user_id].get('watermark_settings')
    
    # Provide options for screenshots or watermark
    keyboard = [
        [InlineKeyboardButton("Take Screenshot", callback_data="screenshot")],
        [InlineKeyboardButton("Add Watermark", callback_data="watermark")]
    ]
    
    # Add quick watermark option if user has saved preferences
    if has_prefs:
        keyboard.append([InlineKeyboardButton("Quick Watermark (Use Saved Settings)", callback_data="quick_watermark")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('What would you like to do with the video?', reply_markup=reply_markup)

def take_screenshot(video_path: str, screenshot_path: str, timestamp=1) -> None:
    """Take a screenshot from the video at the specified timestamp."""
    clip = VideoFileClip(video_path)
    # If timestamp > duration, use mid-point of video
    if timestamp > clip.duration:
        timestamp = clip.duration / 2
    frame = clip.get_frame(timestamp)
    image = Image.fromarray(frame)
    image.save(screenshot_path)
    clip.close()

def take_screenshots(update: Update, context: CallbackContext, timestamp_list=None) -> None:
    """Take screenshots from the video at specified timestamps."""
    if 'video_path' not in context.user_data:
        update.callback_query.message.reply_text('No video found. Please send a video first.')
        return
    
    video_path = context.user_data['video_path']
    progress_msg = context.user_data['progress_msg']
    progress_msg.edit_text('Generating screenshots...')
    
    # If no timestamps are provided, use default values (25%, 50%, 75% of video)
    if not timestamp_list:
        clip = VideoFileClip(video_path)
        duration = clip.duration
        timestamp_list = [duration * 0.25, duration * 0.5, duration * 0.75]
        clip.close()
    
    screenshots = []
    for i, timestamp in enumerate(timestamp_list):
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as screenshot_file:
            screenshot_path = screenshot_file.name
            take_screenshot(video_path, screenshot_path, timestamp)
            screenshots.append(screenshot_path)
            progress_msg.edit_text(f'Generated screenshot {i+1}/{len(timestamp_list)}')
    
    progress_msg.edit_text('Screenshots generated successfully!')
    
    # Send all screenshots
    for i, screenshot_path in enumerate(screenshots):
        caption = f"Screenshot {i+1} (at {int(timestamp_list[i])}s)"
        update.callback_query.message.reply_photo(photo=open(screenshot_path, 'rb'), caption=caption)
        os.remove(screenshot_path)  # Clean up
    
    # Provide options to go back to main menu
    keyboard = [
        [InlineKeyboardButton("Back to Options", callback_data="back_to_options")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.callback_query.message.reply_text('What would you like to do next?', reply_markup=reply_markup)

def add_text_watermark(video_path: str, watermark_text: str, position: str, opacity: float, output_path: str) -> None:
    """Add text watermark to the video."""
    video = VideoFileClip(video_path)
    
    # Create text watermark with specified opacity (0-1)
    watermark = TextClip(watermark_text, fontsize=24, color='white', bg_color='black')
    watermark = watermark.set_opacity(opacity).set_position(position).set_duration(video.duration)
    
    final = CompositeVideoClip([video, watermark])
    final.write_videofile(output_path, logger=None)  # disable logger to avoid spam
    video.close()
    watermark.close()
    final.close()

def add_image_watermark(video_path: str, image_path: str, position: str, opacity: float, output_path: str) -> None:
    """Add image watermark to the video."""
    video = VideoFileClip(video_path)
    
    # Load image watermark and resize it to be proportionate to video
    watermark = ImageClip(image_path)
    video_width = video.size[0]
    watermark_width = video_width * 0.2  # 20% of video width
    watermark = watermark.resize(width=watermark_width)
    
    # Set opacity and position
    watermark = watermark.set_opacity(opacity).set_position(position).set_duration(video.duration)
    
    final = CompositeVideoClip([video, watermark])
    final.write_videofile(output_path, logger=None)  # disable logger to avoid spam
    video.close()
    watermark.close()
    final.close()

def process_with_progress(update: Update, context: CallbackContext, process_func, args, progress_msg):
    """Run a long-running process with progress updates."""
    try:
        # Get video duration to estimate time
        video_path = args[0]  # First argument is video_path
        clip = VideoFileClip(video_path)
        duration = clip.duration
        clip.close()
        
        # Estimate process time (roughly 2x video duration for watermark)
        est_time = int(duration * 2)
        start_time = time.time()
        
        # Start the process in a separate thread
        thread = threading.Thread(target=process_func, args=args)
        thread.start()
        
        # Update progress while the thread is running
        while thread.is_alive():
            elapsed = int(time.time() - start_time)
            if elapsed < est_time:
                progress = min(int((elapsed / est_time) * 100), 95)  # Cap at 95%
                progress_msg.edit_text(f"Processing: {progress}% complete\nEstimated time remaining: {est_time - elapsed}s")
            else:
                progress_msg.edit_text(f"Processing: 95% complete\nAlmost done...")
            time.sleep(3)  # Update every 3 seconds
        
        # Process completed
        progress_msg.edit_text("Processing completed!")
        return True
    except Exception as e:
        progress_msg.edit_text(f"Error during processing: {str(e)}")
        logger.error(f"Error during processing: {e}")
        return False

def button(update: Update, context: CallbackContext) -> None:
    """Handle inline button presses."""
    query = update.callback_query
    query.answer()
    choice = query.data
    user_id = str(query.from_user.id)
    
    if choice == "screenshot":
        # Handle screenshot option
        take_screenshots(update, context)
        
    elif choice == "watermark":
        # Ask for watermark type
        keyboard = [
            [InlineKeyboardButton(wm_type, callback_data=f"wm_type_{wm_type}") for wm_type in WATERMARK_TYPES]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.message.reply_text('Choose watermark type:', reply_markup=reply_markup)
    
    elif choice == "quick_watermark":
        # Use saved watermark settings
        if user_id in user_preferences and 'watermark_settings' in user_preferences[user_id]:
            settings = user_preferences[user_id]['watermark_settings']
            
            # Set up context with saved settings
            context.user_data['wm_type'] = settings['type']
            context.user_data['wm_position'] = settings['position']
            context.user_data['wm_opacity'] = settings['opacity']
            
            if settings['type'] == 'text':
                watermark_text = settings['text']
                video_path = context.user_data['video_path']
                output_path = tempfile.mktemp(suffix='.mp4')
                
                # Create progress message and process
                progress_msg = query.message.reply_text('Starting quick watermark process...')
                
                # Process with progress updates
                success = process_with_progress(
                    update, context, 
                    add_text_watermark, 
                    (video_path, watermark_text, settings['position'], settings['opacity'], output_path),
                    progress_msg
                )
                
                if success:
                    # Upload watermarked video
                    progress_msg.edit_text('Uploading video...')
                    try:
                        with open(output_path, 'rb') as video_file:
                            query.message.reply_video(
                                video=video_file,
                                caption=f"Video with saved text watermark"
                            )
                        progress_msg.edit_text('Upload complete!')
                    except Exception as e:
                        progress_msg.edit_text(f"Error uploading video: {str(e)}")
                        logger.error(f"Error uploading video: {e}")
                
                # Clean up
                try:
                    os.remove(output_path)
                    if os.path.exists(video_path):
                        os.remove(video_path)
                except Exception as e:
                    logger.error(f"Error cleaning up files: {e}")
                
                # Reset user data except for preferences
                context.user_data.clear()
            else:
                query.message.reply_text("Image watermarks are not supported in quick mode. Please use regular watermark option.")
        else:
            query.message.reply_text("No saved watermark settings found. Please use the regular watermark option first.")
    
    elif choice.startswith("wm_type_"):
        # Store watermark type and ask for position
        wm_type = choice.split("_")[2]
        context.user_data['wm_type'] = wm_type
        
        keyboard = [[InlineKeyboardButton(pos, callback_data=f"wm_pos_{pos}") for pos in WATERMARK_POSITIONS[:3]]]
        keyboard.append([InlineKeyboardButton(pos, callback_data=f"wm_pos_{pos}") for pos in WATERMARK_POSITIONS[3:]])
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.message.reply_text('Choose watermark position:', reply_markup=reply_markup)
    
    elif choice.startswith("wm_pos_"):
        # Store position and ask for opacity
        position = choice.split("_")[2]
        context.user_data['wm_position'] = position
        
        keyboard = [[InlineKeyboardButton(op, callback_data=f"wm_op_{op}") for op in WATERMARK_OPACITY]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.message.reply_text('Choose watermark opacity:', reply_markup=reply_markup)
    
    elif choice.startswith("wm_op_"):
        # Store opacity and ask for text/image
        opacity_str = choice.split("_")[2]
        # Convert percentage to decimal
        opacity = float(opacity_str.strip('%')) / 100
        context.user_data['wm_opacity'] = opacity
        
        wm_type = context.user_data.get('wm_type', 'text')
        if wm_type == 'text':
            # Add option to save settings
            keyboard = [
                [InlineKeyboardButton("Yes, save these settings", callback_data="save_settings")],
                [InlineKeyboardButton("No, just use once", callback_data="dont_save_settings")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.message.reply_text('Do you want to save these watermark settings for future use?', reply_markup=reply_markup)
        else:
            query.message.reply_text('Please upload an image to use as watermark:')
            context.user_data['awaiting_input'] = 'watermark_image'
    
    elif choice == "save_settings":
        # Save current watermark settings
        if user_id not in user_preferences:
            user_preferences[user_id] = {}
            
        user_preferences[user_id]['watermark_settings'] = {
            'type': context.user_data['wm_type'],
            'position': context.user_data['wm_position'],
            'opacity': context.user_data['wm_opacity']
        }
        
        query.message.reply_text('Please enter the text for the watermark:')
        context.user_data['awaiting_input'] = 'watermark_text'
        context.user_data['save_settings'] = True
    
    elif choice == "dont_save_settings":
        query.message.reply_text('Please enter the text for the watermark:')
        context.user_data['awaiting_input'] = 'watermark_text'
        context.user_data['save_settings'] = False
    
    elif choice == "back_to_options":
        # Return to the main options menu
        keyboard = [
            [InlineKeyboardButton("Take Screenshot", callback_data="screenshot")],
            [InlineKeyboardButton("Add Watermark", callback_data="watermark")]
        ]
        
        # Add quick watermark option if user has saved preferences
        if user_id in user_preferences and 'watermark_settings' in user_preferences[user_id]:
            keyboard.append([InlineKeyboardButton("Quick Watermark (Use Saved Settings)", callback_data="quick_watermark")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.message.reply_text('What would you like to do with the video?', reply_markup=reply_markup)

def handle_text(update: Update, context: CallbackContext) -> None:
    """Handle text messages."""
    if 'awaiting_input' not in context.user_data:
        update.message.reply_text('Send me a video file first or use /start to begin.')
        return
    
    if context.user_data['awaiting_input'] == 'watermark_text':
        user_id = str(update.effective_user.id)
        watermark_text = update.message.text
        video_path = context.user_data['video_path']
        position = context.user_data['wm_position']
        opacity = context.user_data['wm_opacity']
        
        # Save text in user preferences if requested
        if context.user_data.get('save_settings', False):
            if user_id not in user_preferences:
                user_preferences[user_id] = {}
            if 'watermark_settings' not in user_preferences[user_id]:
                user_preferences[user_id]['watermark_settings'] = {}
                
            user_preferences[user_id]['watermark_settings']['text'] = watermark_text
            save_user_preferences(user_preferences)
            update.message.reply_text('Your watermark settings have been saved for future use.')
        
        # Create temp file for output
        output_path = tempfile.mktemp(suffix='.mp4')
            
        # Create progress message and update it during processing
        progress_msg = update.message.reply_text('Starting watermark process...')
        
        # Process with progress updates
        success = process_with_progress(
            update, context, 
            add_text_watermark, 
            (video_path, watermark_text, position, opacity, output_path),
            progress_msg
        )
        
        if success:
            # Upload watermarked video
            progress_msg.edit_text('Uploading video...')
            try:
                with open(output_path, 'rb') as video_file:
                    update.message.reply_video(
                        video=video_file,
                        caption=f"Video with text watermark at {position}, opacity: {int(opacity*100)}%"
                    )
                progress_msg.edit_text('Upload complete!')
            except Exception as e:
                progress_msg.edit_text(f"Error uploading video: {str(e)}")
                logger.error(f"Error uploading video: {e}")
        
        # Clean up
        try:
            os.remove(output_path)
            if os.path.exists(video_path):
                os.remove(video_path)
        except Exception as e:
            logger.error(f"Error cleaning up files: {e}")
        
        # Reset user data except for preferences
        context.user_data.clear()
        
        # Offer to start over
        update.message.reply_text('Done! Send another video to start again or use /start command.')

def handle_photo(update: Update, context: CallbackContext) -> None:
    """Handle photo uploads for image watermarks."""
    if 'awaiting_input' not in context.user_data or context.user_data['awaiting_input'] != 'watermark_image':
        update.message.reply_text('Send me a video file first or use /start to begin.')
        return
    
    # Download the largest version of the photo
    photo_file = update.message.photo[-1].get_file()
    image_path = tempfile.mktemp(suffix='.jpg')
    photo_file.download(image_path)
    
    video_path = context.user_data['video_path']
    position = context.user_data['wm_position']
    opacity = context.user_data['wm_opacity']
    
    # Create temp file for output
    output_path = tempfile.mktemp(suffix='.mp4')
    
    # Create progress message and update it during processing
    progress_msg = update.message.reply_text('Starting watermark process...')
    
    # Process with progress updates
    success = process_with_progress(
        update, context, 
        add_image_watermark, 
        (video_path, image_path, position, opacity, output_path),
        progress_msg
    )
    
    if success:
        # Upload watermarked video
        progress_msg.edit_text('Uploading video...')
        try:
            with open(output_path, 'rb') as video_file:
                update.message.reply_video(
                    video=video_file, 
                    caption=f"Video with image watermark at {position}, opacity: {int(opacity*100)}%"
                )
            progress_msg.edit_text('Upload complete!')
        except Exception as e:
            progress_msg.edit_text(f"Error uploading video: {str(e)}")
            logger.error(f"Error uploading video: {e}")
    
    # Clean up
    try:
        os.remove(output_path)
        os.remove(image_path)
        if os.path.exists(video_path):
            os.remove(video_path)
    except Exception as e:
        logger.error(f"Error cleaning up files: {e}")
    
    # Reset user data
    context.user_data.clear()
    
    # Offer to start over
    update.message.reply_text('Done! Send another video to start again or use /start command.')

# Add command to clear saved preferences
def clear_preferences(update: Update, context: CallbackContext) -> None:
    """Clear saved preferences for the user."""
    user_id = str(update.effective_user.id)
    if user_id in user_preferences:
        del user_preferences[user_id]
        save_user_preferences(user_preferences)
        update.message.reply_text('Your saved preferences have been cleared.')
    else:
        update.message.reply_text('You have no saved preferences.')

def main() -> None:
    """Start the bot."""
    try:
        logger.info("Starting bot...")
        updater = Updater(TOKEN)
        
        dispatcher = updater.dispatcher

        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(CommandHandler("clear_preferences", clear_preferences))
        dispatcher.add_handler(MessageHandler(Filters.video, handle_video))
        dispatcher.add_handler(CallbackQueryHandler(button))
        dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
        dispatcher.add_handler(MessageHandler(Filters.photo, handle_photo))

        logger.info("Bot started successfully!")
        updater.start_polling()
        updater.idle()
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
