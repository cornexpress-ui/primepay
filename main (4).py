import os
import logging
import sys
import uuid
import tempfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler
from PIL import Image, ImageDraw, ImageFont
import pymongo
from datetime import datetime
import subprocess

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define constants
WATERMARK_POSITIONS = ['upper-left', 'upper-right', 'lower-left', 'lower-right', 'center']
WATERMARK_OPACITY = ['25%', '50%', '75%', '100%']

# Get environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_CHANNEL_ID = os.getenv("DATABASE_CHANNEL_ID")

# Validate required environment variables
if not TOKEN:
    logger.error("No TELEGRAM_BOT_TOKEN environment variable found!")
    sys.exit(1)

# MongoDB setup
mongo_client = None
db = None
if MONGODB_URI:
    try:
        mongo_client = pymongo.MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        # Test connection
        mongo_client.server_info()
        db = mongo_client.watermark_bot
        logger.info("Connected to MongoDB successfully!")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        db = None

def get_user_preferences(user_id):
    """Get user preferences from MongoDB"""
    if db is not None:
        try:
            return db.user_preferences.find_one({"user_id": user_id})
        except Exception as e:
            logger.error(f"Error getting user preferences from MongoDB: {e}")
    return None

def save_user_preferences(user_id, preferences):
    """Save user preferences to MongoDB"""
    if db is not None:
        try:
            db.user_preferences.update_one(
                {"user_id": user_id},
                {"$set": preferences},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error saving user preferences to MongoDB: {e}")
    return False

def log_processing(user_id, action, status, details=None):
    """Log bot actions to MongoDB"""
    if db is not None:
        try:
            db.logs.insert_one({
                "user_id": user_id,
                "action": action,
                "status": status,
                "details": details,
                "timestamp": datetime.utcnow()
            })
        except Exception as e:
            logger.error(f"Error logging to MongoDB: {e}")

def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    user_id = str(update.effective_user.id)
    update.message.reply_text('Hi! Send me a video file to get started.')
    log_processing(user_id, "start", "success")

def handle_video(update: Update, context: CallbackContext) -> None:
    """Handle the video file sent by the user."""
    user_id = str(update.effective_user.id)
    
    progress_msg = update.message.reply_text('Processing video...')
    
    try:
        # Check video size
        video_size_mb = update.message.video.file_size / (1024 * 1024)
        if video_size_mb > 50:
            progress_msg.edit_text(f'Video is too large ({video_size_mb:.1f} MB). Maximum allowed size is 50 MB.')
            return
        
        # Get and store file_id for later use
        file_id = update.message.video.file_id
        duration = update.message.video.duration
        
        # Store in user_data
        context.user_data['video_file_id'] = file_id
        context.user_data['video_duration'] = duration
        context.user_data['progress_msg'] = progress_msg
        
        # Check if user has saved preferences
        user_prefs = get_user_preferences(user_id)
        has_prefs = user_prefs is not None and 'watermark_settings' in user_prefs
        
        # Show options
        keyboard = [
            [InlineKeyboardButton("Take Screenshot", callback_data="screenshot")],
            [InlineKeyboardButton("Add Watermark Info", callback_data="watermark")]
        ]
        
        # Add quick watermark option if user has saved preferences
        if has_prefs:
            keyboard.append([InlineKeyboardButton("Use Saved Watermark", callback_data="quick_watermark")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        progress_msg.edit_text(f'Video received! Size: {video_size_mb:.1f} MB, Duration: {duration} seconds')
        update.message.reply_text('What would you like to do?', reply_markup=reply_markup)
        
        log_processing(user_id, "video_upload", "success", {
            "file_id": file_id,
            "file_size": update.message.video.file_size,
            "duration": duration
        })
    except Exception as e:
        progress_msg.edit_text(f"Error processing video: {str(e)}")
        logger.error(f"Error in handle_video: {e}")
        log_processing(user_id, "video_upload", "error", {"error": str(e)})

def take_screenshots_at_positions(update: Update, context: CallbackContext) -> None:
    """Take screenshots at the beginning, middle and end of the video."""
    user_id = str(update.callback_query.from_user.id)
    
    if 'video_file_id' not in context.user_data:
        update.callback_query.message.reply_text('No video found. Please send a video first.')
        return
    
    progress_msg = update.callback_query.message.reply_text('Processing screenshots...')
    
    try:
        # Get video info
        file_id = context.user_data['video_file_id']
        duration = context.user_data.get('video_duration', 10)
        
        # Get the file
        file = context.bot.get_file(file_id)
        
        # Create temp dir
        temp_dir = tempfile.mkdtemp()
        video_path = os.path.join(temp_dir, f"video_{uuid.uuid4().hex}.mp4")
        
        # Download the video
        file.download(video_path)
        
        # Calculate screenshot positions
        positions = [
            ("Beginning", 1),
            ("Middle", duration // 2),
            ("End", max(1, duration - 3))
        ]
        
        # Take screenshots
        screenshots_taken = 0
        for position_name, timestamp in positions:
            try:
                # Create screenshot path
                screenshot_path = os.path.join(temp_dir, f"screenshot_{uuid.uuid4().hex}.jpg")
                
                # Use ffmpeg to take screenshot
                cmd = [
                    'ffmpeg',
                    '-y',
                    '-ss', str(timestamp),
                    '-i', video_path,
                    '-vframes', '1',
                    '-q:v', '2',
                    screenshot_path
                ]
                
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
                
                # Check if screenshot was created
                if os.path.exists(screenshot_path) and os.path.getsize(screenshot_path) > 0:
                    # Send the screenshot
                    with open(screenshot_path, 'rb') as photo:
                        update.callback_query.message.reply_photo(
                            photo=photo, 
                            caption=f"{position_name} of video (at {timestamp}s)"
                        )
                    screenshots_taken += 1
                    
                    # Clean up
                    os.remove(screenshot_path)
                    
            except Exception as e:
                logger.error(f"Error taking screenshot at {timestamp}s: {e}")
                
        # Clean up video
        try:
            os.remove(video_path)
            os.rmdir(temp_dir)
        except:
            pass
        
        if screenshots_taken > 0:
            progress_msg.edit_text(f'Successfully created {screenshots_taken} screenshots.')
            log_processing(user_id, "screenshots", "success", {"count": screenshots_taken})
        else:
            progress_msg.edit_text('Failed to create screenshots. Try a different video format.')
            log_processing(user_id, "screenshots", "error", {"error": "No screenshots created"})
            
        # Back to options button
        keyboard = [
            [InlineKeyboardButton("Back to Options", callback_data="back_to_options")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.callback_query.message.reply_text('What would you like to do next?', reply_markup=reply_markup)
        
    except Exception as e:
        progress_msg.edit_text(f"Error processing screenshots: {str(e)}")
        logger.error(f"Error in take_screenshots: {e}")
        log_processing(user_id, "screenshots", "error", {"error": str(e)})

def button(update: Update, context: CallbackContext) -> None:
    """Handle inline button presses."""
    user_id = str(update.callback_query.from_user.id)
    query = update.callback_query
    query.answer()
    choice = query.data
    
    if choice == "screenshot":
        # Take screenshots at different positions
        take_screenshots_at_positions(update, context)
        
    elif choice == "watermark":
        # Ask for watermark position
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
        # Store opacity and ask for saving preference
        opacity_str = choice.split("_")[2]
        opacity = float(opacity_str.strip('%')) / 100
        context.user_data['wm_opacity'] = opacity
        
        # Ask to save settings
        keyboard = [
            [InlineKeyboardButton("Yes, save these settings", callback_data="save_settings")],
            [InlineKeyboardButton("No, just use once", callback_data="dont_save_settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.message.reply_text('Do you want to save these watermark settings?', reply_markup=reply_markup)
        
    elif choice == "save_settings":
        # Save settings
        settings = {
            "watermark_settings": {
                'position': context.user_data['wm_position'],
                'opacity': context.user_data['wm_opacity']
            }
        }
        save_user_preferences(user_id, settings)
        
        query.message.reply_text('Please enter the text for the watermark:')
        context.user_data['awaiting_input'] = 'watermark_text'
        context.user_data['save_settings'] = True
        
    elif choice == "dont_save_settings":
        query.message.reply_text('Please enter the text for the watermark:')
        context.user_data['awaiting_input'] = 'watermark_text'
        context.user_data['save_settings'] = False
        
    elif choice == "quick_watermark":
        # Use saved settings
        user_prefs = get_user_preferences(user_id)
        if user_prefs is not None and 'watermark_settings' in user_prefs:
            settings = user_prefs['watermark_settings']
            
            # Apply saved settings
            if 'text' in settings:
                # Get info
                video_file_id = context.user_data['video_file_id']
                watermark_text = settings['text']
                position = settings['position']
                opacity = settings['opacity']
                
                # Send video back with caption
                caption = f"Video with watermark text: '{watermark_text}'\nPosition: {position}\nOpacity: {int(opacity*100)}%"
                
                try:
                    # First try to store in database channel if available
                    if DATABASE_CHANNEL_ID is not None:
                        try:
                            channel_id = DATABASE_CHANNEL_ID
                            if isinstance(channel_id, str) and not channel_id.startswith('-100') and not channel_id.startswith('-'):
                                channel_id = f"-100{channel_id}"
                                
                            context.bot.send_video(
                                chat_id=channel_id,
                                video=video_file_id,
                                caption=f"User ID: {user_id}\nWatermark: {watermark_text}\nPosition: {position}\nOpacity: {int(opacity*100)}%"
                            )
                        except Exception as e:
                            logger.error(f"Error sending to database channel: {e}")
                    
                    # Send to user
                    context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=video_file_id,
                        caption=caption
                    )
                    
                    # Create visual preview
                    create_watermark_preview(update, context, watermark_text, position, opacity)
                    
                    query.message.reply_text('Done! This is a preview of how your watermark would appear.')
                    log_processing(user_id, "quick_watermark", "success")
                    
                except Exception as e:
                    query.message.reply_text(f"Error applying quick watermark: {str(e)}")
                    logger.error(f"Error in quick_watermark: {e}")
                    log_processing(user_id, "quick_watermark", "error", {"error": str(e)})
            else:
                query.message.reply_text("Saved settings are incomplete. Please use the regular watermark option first.")
        else:
            query.message.reply_text("No saved watermark settings found. Please use the regular watermark option first.")
    
    elif choice == "back_to_options":
        # Return to main options
        if 'video_file_id' not in context.user_data:
            query.message.reply_text('No video found. Please send a video first.')
            return
            
        # Check if user has saved preferences
        user_prefs = get_user_preferences(user_id)
        has_prefs = user_prefs is not None and 'watermark_settings' in user_prefs
        
        # Show options
        keyboard = [
            [InlineKeyboardButton("Take Screenshot", callback_data="screenshot")],
            [InlineKeyboardButton("Add Watermark Info", callback_data="watermark")]
        ]
        
        # Add quick watermark option if user has saved preferences
        if has_prefs:
            keyboard.append([InlineKeyboardButton("Use Saved Watermark", callback_data="quick_watermark")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.message.reply_text('What would you like to do?', reply_markup=reply_markup)

def create_watermark_preview(update, context, text, position, opacity):
    """Create a visual preview of how the watermark would look."""
    try:
        # Create a sample frame
        width, height = 640, 360
        img = Image.new('RGB', (width, height), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Add some visual elements to make it look like a video frame
        draw.rectangle([20, 20, width-20, height-20], outline=(50, 50, 50), width=2)
        draw.line([(width//2, 20), (width//2, height-20)], fill=(50, 50, 50), width=1)
        draw.line([(20, height//2), (width-20, height//2)], fill=(50, 50, 50), width=1)
        
        # Position the watermark text
        font_size = 24
        try:
            # Try to load a font if available
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            # Otherwise use default
            font = ImageFont.load_default()
            
        text_width = draw.textlength(text, font=font) if hasattr(draw, 'textlength') else font_size * len(text) * 0.6
        
        if position == 'upper-left':
            pos = (20, 20)
        elif position == 'upper-right':
            pos = (width - text_width - 20, 20)
        elif position == 'lower-left':
            pos = (20, height - font_size - 20)
        elif position == 'lower-right':
            pos = (width - text_width - 20, height - font_size - 20)
        else:  # center
            pos = ((width - text_width) // 2, (height - font_size) // 2)
        
        # Draw background rectangle
        draw.rectangle([pos[0]-5, pos[1]-5, pos[0] + text_width + 5, pos[1] + font_size + 5], 
                      fill=(0, 0, 0))
        
        # Draw text
        draw.text(pos, text, font=font, fill=(int(255*opacity), int(255*opacity), int(255*opacity)))
        
        # Save and send
        temp_path = os.path.join(tempfile.gettempdir(), f"preview_{uuid.uuid4()}.jpg")
        img.save(temp_path)
        
        with open(temp_path, 'rb') as f:
            if hasattr(update, 'callback_query'):
                update.callback_query.message.reply_photo(
                    photo=f,
                    caption=f"Preview of watermark: '{text}' at {position} with {int(opacity*100)}% opacity"
                )
            else:
                update.message.reply_photo(
                    photo=f,
                    caption=f"Preview of watermark: '{text}' at {position} with {int(opacity*100)}% opacity"
                )
        
        # Clean up
        os.remove(temp_path)
        
    except Exception as e:
        logger.error(f"Error creating watermark preview: {e}")

def handle_text(update: Update, context: CallbackContext) -> None:
    """Handle text messages."""
    user_id = str(update.effective_user.id)
    
    if 'awaiting_input' not in context.user_data:
        update.message.reply_text('Send me a video file first or use /start to begin.')
        return
    
    if context.user_data['awaiting_input'] == 'watermark_text':
        watermark_text = update.message.text
        video_file_id = context.user_data['video_file_id']
        position = context.user_data['wm_position']
        opacity = context.user_data['wm_opacity']
        
        # Save in user preferences if requested
        if context.user_data.get('save_settings', False):
            if db is not None:
                try:
                    db.user_preferences.update_one(
                        {"user_id": user_id},
                        {"$set": {"watermark_settings.text": watermark_text}}
                    )
                    update.message.reply_text('Your watermark settings have been saved for future use.')
                except Exception as e:
                    logger.error(f"Error saving watermark text: {e}")
        
        progress_msg = update.message.reply_text('Processing...')
        
        try:
            # Send original video with caption indicating the watermark
            caption = f"Video with watermark text: '{watermark_text}'\nPosition: {position}\nOpacity: {int(opacity*100)}%"
            
            # First, try saving to database channel if available
            if DATABASE_CHANNEL_ID is not None:
                try:
                    channel_id = DATABASE_CHANNEL_ID
                    if isinstance(channel_id, str) and not channel_id.startswith('-100') and not channel_id.startswith('-'):
                        channel_id = f"-100{channel_id}"
                        
                    context.bot.send_video(
                        chat_id=channel_id,
                        video=video_file_id,
                        caption=f"User ID: {user_id}\nWatermark: {watermark_text}\nPosition: {position}\nOpacity: {int(opacity*100)}%"
                    )
                except Exception as e:
                    logger.error(f"Error sending to database channel: {e}")
            
            # Now send to user
            context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video_file_id,
                caption=caption
            )
            
            progress_msg.edit_text('Video sent! This is a preview of how your video would look with the watermark.')
            
            # Create and send watermark preview
            create_watermark_preview(update, context, watermark_text, position, opacity)
            
            log_processing(user_id, "watermark_text", "success", {
                "text": watermark_text,
                "position": position,
                "opacity": opacity
            })
            
        except Exception as e:
            progress_msg.edit_text(f"Error applying watermark: {str(e)}")
            logger.error(f"Error in handle_watermark_text: {e}")
            log_processing(user_id, "watermark_text", "error", {"error": str(e)})
        
        # Reset user data
        context.user_data.clear()
        
        # Offer to start over
        update.message.reply_text('Done! Send another video to start again or use /start command.')

def clear_preferences(update: Update, context: CallbackContext) -> None:
    """Clear saved preferences for the user."""
    user_id = str(update.effective_user.id)
    
    if db is not None:
        try:
            db.user_preferences.delete_one({"user_id": user_id})
            update.message.reply_text('Your saved preferences have been cleared.')
            log_processing(user_id, "clear_preferences", "success")
        except Exception as e:
            logger.error(f"Error clearing preferences: {e}")
            update.message.reply_text('Failed to clear your preferences. Please try again.')
    else:
        update.message.reply_text('Database not available. Your preferences could not be cleared.')

def help_command(update: Update, context: CallbackContext) -> None:
    """Provide help information about using the bot."""
    help_text = """
*Video Watermark Bot - Light Version*

This bot allows you to take screenshots and save watermark information for videos.

*Basic Commands:*
/start - Start the bot
/help - Show this help message
/clear_preferences - Clear your saved watermark settings

*How to use:*
1. Send a video file to the bot
2. Choose one of the options:
   • Take Screenshot - Generate screenshots from your video
   • Add Watermark Info - Add text watermark information
   • Use Saved Watermark - Apply your previously saved settings

*Note:* This is a lightweight version of the bot. It doesn't actually process videos with watermarks due to Heroku limitations.

*Tips:*
• For best results, use videos under 50MB
• You can save your favorite watermark settings for quick use next time
    """
    update.message.reply_text(help_text, parse_mode='Markdown')

def setup_command(update: Update, context: CallbackContext) -> None:
    """Admin command to set up the database channel."""
    if not context.args or len(context.args) != 1:
        update.message.reply_text('Usage: /setup channel_id')
        return
    
    channel_id = context.args[0]
    
    # Ensure proper format for channel ID
    if not channel_id.startswith('-100') and not channel_id.startswith('-'):
        formatted_channel_id = f"-100{channel_id}"
    else:
        formatted_channel_id = channel_id
    
    # Try to send a test message to verify bot has access
    try:
        test_msg = context.bot.send_message(
            chat_id=formatted_channel_id,
            text=f"Bot setup initiated by user {update.effective_user.id}. This channel will be used as a database."
        )
        
        # If successful, save the channel ID
        if db is not None:
            db.config.update_one(
                {"key": "database_channel"},
                {"$set": {"value": formatted_channel_id}},
                upsert=True
            )
        
        # Set the global variable
        global DATABASE_CHANNEL_ID
        DATABASE_CHANNEL_ID = formatted_channel_id
        
        update.message.reply_text(f'Database channel successfully set up! Channel ID: {formatted_channel_id}')
    except Exception as e:
        update.message.reply_text(f'Failed to set up channel: {str(e)}\n\nMake sure the bot is an admin in the channel.')

def main() -> None:
    """Start the bot."""
    try:
        logger.info("Starting bot...")
        updater = Updater(TOKEN)
        
        dispatcher = updater.dispatcher

        # Basic commands
        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(CommandHandler("help", help_command))
        dispatcher.add_handler(CommandHandler("clear_preferences", clear_preferences))
        
        # Admin commands
        dispatcher.add_handler(CommandHandler("setup", setup_command))
        
        # Message handlers
        dispatcher.add_handler(MessageHandler(Filters.video, handle_video))
        dispatcher.add_handler(CallbackQueryHandler(button))
        dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

        # Load database channel ID from MongoDB if available
        global DATABASE_CHANNEL_ID
        if db is not None and DATABASE_CHANNEL_ID is None:
            config = db.config.find_one({"key": "database_channel"})
            if config and "value" in config:
                DATABASE_CHANNEL_ID = config["value"]
                logger.info(f"Loaded database channel ID from MongoDB: {DATABASE_CHANNEL_ID}")

        logger.info("Bot started successfully!")
        updater.start_polling()
        updater.idle()
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()