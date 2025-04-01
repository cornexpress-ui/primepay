import os
import logging
import sys
import time
import json
import signal
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, ImageClip
from moviepy.config import change_settings
from moviepy.video.fx.all import resize
from PIL import Image
import tempfile
import threading
import pymongo
from datetime import datetime
import uuid
import subprocess

# Configure MoviePy to use less memory
change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define constants for watermark positions
WATERMARK_POSITIONS = ['upper-left', 'upper-right', 'lower-left', 'lower-right', 'center']
WATERMARK_TYPES = ['text', 'image']
WATERMARK_OPACITY = ['25%', '50%', '75%', '100%']
PROCESSING_TIMEOUT = 180  # Maximum processing time in seconds

# Get environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_CHANNEL_ID = os.getenv("DATABASE_CHANNEL_ID")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

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
        # Test the connection
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
    
    progress_msg = update.message.reply_text('Downloading video...')
    
    try:
        # Check video size first
        video_size_mb = update.message.video.file_size / (1024 * 1024)
        if video_size_mb > 50:
            progress_msg.edit_text(f'Video is too large ({video_size_mb:.1f} MB). The maximum allowed size is 50 MB.')
            return
            
        # Download video with progress updates
        video_file = update.message.video.get_file()
        
        # Create a directory for this user if it doesn't exist
        user_temp_dir = os.path.join(tempfile.gettempdir(), f"user_{user_id}")
        os.makedirs(user_temp_dir, exist_ok=True)
        
        # Download to user-specific directory with unique filename
        video_filename = f"video_{uuid.uuid4().hex}.mp4"
        video_path = os.path.join(user_temp_dir, video_filename)
        video_file.download(video_path)
        
        # Verify the file was downloaded correctly
        if not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
            progress_msg.edit_text('Error downloading video. Please try again.')
            return
            
        progress_msg.edit_text(f'Video downloaded successfully! Size: {video_size_mb:.1f} MB')
        
        # Store the video path in user_data
        context.user_data['video_path'] = video_path
        context.user_data['progress_msg'] = progress_msg
        context.user_data['video_size'] = video_size_mb
        
        # Check if user has saved preferences
        user_prefs = get_user_preferences(user_id)
        has_prefs = user_prefs is not None and 'watermark_settings' in user_prefs
        
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
        
        log_processing(user_id, "video_upload", "success", {
            "file_id": update.message.video.file_id,
            "file_size": update.message.video.file_size,
            "duration": update.message.video.duration
        })
    except Exception as e:
        progress_msg.edit_text(f"Error processing video: {str(e)}")
        logger.error(f"Error in handle_video: {e}")
        log_processing(user_id, "video_upload", "error", {"error": str(e)})

def take_screenshot(video_path: str, screenshot_path: str, timestamp=1) -> bool:
    """Take a screenshot from the video."""
    try:
        # Use ffmpeg directly instead of MoviePy for better performance
        cmd = [
            'ffmpeg',
            '-y',  # Overwrite output file if it exists
            '-ss', str(timestamp),  # Seek to this position
            '-i', video_path,  # Input file
            '-vframes', '1',  # Extract one frame
            '-q:v', '2',  # Quality level (lower is better)
            screenshot_path  # Output file
        ]
        
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return os.path.exists(screenshot_path)
    except Exception as e:
        logger.error(f"Error taking screenshot with ffmpeg: {e}")
        
        # Fallback to MoviePy if ffmpeg direct call fails
        try:
            clip = VideoFileClip(video_path)
            # If timestamp > duration, use mid-point of video
            if timestamp > clip.duration:
                timestamp = clip.duration / 2
            frame = clip.get_frame(timestamp)
            image = Image.fromarray(frame)
            image.save(screenshot_path)
            clip.close()
            return os.path.exists(screenshot_path)
        except Exception as e2:
            logger.error(f"Error taking screenshot with MoviePy: {e2}")
            return False

def take_screenshots(update: Update, context: CallbackContext, timestamp_list=None) -> None:
    """Take screenshots from the video at specified timestamps."""
    user_id = str(update.callback_query.from_user.id)
    
    if 'video_path' not in context.user_data:
        update.callback_query.message.reply_text('No video found. Please send a video first.')
        log_processing(user_id, "screenshot", "error", {"error": "No video found"})
        return
    
    video_path = context.user_data['video_path']
    progress_msg = context.user_data['progress_msg']
    progress_msg.edit_text('Generating screenshots...')
    
    try:
        # If no timestamps are provided, use default values (25%, 50%, 75% of video)
        if not timestamp_list:
            # Get video duration using ffprobe
            try:
                cmd = [
                    'ffprobe', 
                    '-v', 'error',
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    video_path
                ]
                duration = float(subprocess.check_output(cmd).decode('utf-8').strip())
            except:
                # Fallback to moviepy
                clip = VideoFileClip(video_path)
                duration = clip.duration
                clip.close()
                
            timestamp_list = [duration * 0.25, duration * 0.5, duration * 0.75]
        
        # Create a directory for screenshots if it doesn't exist
        user_temp_dir = os.path.dirname(video_path)
        screenshots = []
        
        for i, timestamp in enumerate(timestamp_list):
            screenshot_path = os.path.join(user_temp_dir, f"screenshot_{uuid.uuid4().hex}.png")
            if take_screenshot(video_path, screenshot_path, timestamp):
                screenshots.append((screenshot_path, timestamp))
                progress_msg.edit_text(f'Generated screenshot {i+1}/{len(timestamp_list)}')
            else:
                progress_msg.edit_text(f'Failed to generate screenshot {i+1}. Continuing...')
        
        if screenshots:
            progress_msg.edit_text('Screenshots generated successfully!')
            
            # Send all screenshots
            for i, (screenshot_path, timestamp) in enumerate(screenshots):
                caption = f"Screenshot {i+1} (at {int(timestamp)}s)"
                try:
                    with open(screenshot_path, 'rb') as photo:
                        update.callback_query.message.reply_photo(photo=photo, caption=caption)
                    os.remove(screenshot_path)  # Clean up
                except Exception as e:
                    logger.error(f"Error sending screenshot: {e}")
            
            log_processing(user_id, "screenshot", "success", {
                "count": len(screenshots),
                "timestamps": [int(t) for _, t in screenshots]
            })
        else:
            progress_msg.edit_text('Failed to generate any screenshots.')
            log_processing(user_id, "screenshot", "error", {"error": "Failed to generate screenshots"})
        
        # Provide options to go back to main menu
        keyboard = [
            [InlineKeyboardButton("Back to Options", callback_data="back_to_options")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.callback_query.message.reply_text('What would you like to do next?', reply_markup=reply_markup)
    except Exception as e:
        progress_msg.edit_text(f"Error generating screenshots: {str(e)}")
        logger.error(f"Error in take_screenshots: {e}")
        log_processing(user_id, "screenshot", "error", {"error": str(e)})

def use_ffmpeg_for_watermark(video_path, text, position, opacity, output_path):
    """Add text watermark using ffmpeg directly."""
    try:
        # Convert position to ffmpeg coordinates
        position_map = {
            'upper-left': '10:10',
            'upper-right': 'w-tw-10:10',
            'lower-left': '10:h-th-10',
            'lower-right': 'w-tw-10:h-th-10',
            'center': '(w-tw)/2:(h-th)/2'
        }
        pos = position_map.get(position, '10:10')
        
        # Convert opacity to ffmpeg format (0-1)
        opacity_value = str(opacity)
        
        # Command to add text watermark
        cmd = [
            'ffmpeg',
            '-y',
            '-i', video_path,
            '-vf', f"drawtext=text='{text}':fontcolor=white:fontsize=24:box=1:boxcolor=black@{opacity_value}:x={pos}:y={pos}",
            '-c:a', 'copy',
            output_path
        ]
        
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return os.path.exists(output_path)
    except Exception as e:
        logger.error(f"Error using ffmpeg for watermark: {e}")
        return False

def add_text_watermark(video_path: str, watermark_text: str, position: str, opacity: float, output_path: str) -> bool:
    """Add text watermark to the video."""
    # First try with ffmpeg direct approach (much faster)
    if use_ffmpeg_for_watermark(video_path, watermark_text, position, opacity, output_path):
        return True
        
    # If ffmpeg approach fails, fallback to MoviePy
    try:
        video = VideoFileClip(video_path)
        
        # Create text watermark with specified opacity (0-1)
        watermark = TextClip(watermark_text, fontsize=24, color='white', bg_color='black')
        watermark = watermark.set_opacity(opacity).set_position(position).set_duration(video.duration)
        
        final = CompositeVideoClip([video, watermark])
        final.write_videofile(output_path, codec='libx264', audio_codec='aac', logger=None)
        
        # Ensure everything is closed properly
        video.close()
        watermark.close()
        final.close()
        
        return os.path.exists(output_path)
    except Exception as e:
        logger.error(f"Error adding text watermark with MoviePy: {e}")
        return False

def add_image_watermark(video_path: str, image_path: str, position: str, opacity: float, output_path: str) -> bool:
    """Add image watermark to the video."""
    try:
        video = VideoFileClip(video_path)
        
        # Load image watermark and resize it to be proportionate to video
        watermark = ImageClip(image_path)
        video_width = video.size[0]
        watermark_width = video_width * 0.2  # 20% of video width
        watermark = watermark.resize(width=watermark_width)
        
        # Set opacity and position
        watermark = watermark.set_opacity(opacity).set_position(position).set_duration(video.duration)
        
        final = CompositeVideoClip([video, watermark])
        final.write_videofile(output_path, codec='libx264', audio_codec='aac', logger=None)
        
        # Ensure everything is closed properly
        video.close()
        watermark.close()
        final.close()
        
        return os.path.exists(output_path)
    except Exception as e:
        logger.error(f"Error adding image watermark: {e}")
        return False

class TimedOutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimedOutException("Processing timed out")

def process_with_progress(update: Update, context: CallbackContext, process_func, args, progress_msg):
    """Run a long-running process with progress updates and timeout handling."""
    user_id = str(update.effective_user.id if hasattr(update, 'effective_user') else 
                  update.callback_query.from_user.id)
    
    try:
        # Get video duration to estimate time
        video_path = args[0]  # First argument is video_path
        
        # Get video size from user data
        video_size_mb = context.user_data.get('video_size', 20)  # Default to 20MB if unknown
        
        # Calculate estimated time based on video size
        # Roughly 2 seconds per MB plus 10 seconds baseline
        est_time = int(video_size_mb * 2) + 10
        
        # Ensure we don't exceed maximum processing time
        if est_time > PROCESSING_TIMEOUT:
            est_time = PROCESSING_TIMEOUT
        
        start_time = time.time()
        
        # Start the process in a separate thread
        result = [False]  # Use a list to store the result so it can be modified by the thread
        processing_exception = [None]  # To store any exception that occurs during processing
        
        def process_and_store_result():
            try:
                result[0] = process_func(*args)
            except Exception as e:
                processing_exception[0] = e
                result[0] = False
        
        processing_thread = threading.Thread(target=process_and_store_result)
        processing_thread.daemon = True  # Mark as daemon so it doesn't block program exit
        processing_thread.start()
        
        # Set a maximum time for processing
        processing_timeout = min(PROCESSING_TIMEOUT, est_time * 2)  # Double the estimated time, up to max
        
        # Update progress while the thread is running
        progress_steps = 0
        while processing_thread.is_alive():
            elapsed = int(time.time() - start_time)
            
            # Check if we've exceeded the timeout
            if elapsed > processing_timeout:
                progress_msg.edit_text(f"Processing is taking too long and may have stalled. Please try again with a smaller video.")
                log_processing(user_id, "watermark_process", "timeout", {"timeout": processing_timeout})
                # We won't force-terminate the thread, but we'll stop waiting for it
                return False
            
            if elapsed < est_time:
                progress = min(int((elapsed / est_time) * 100), 95)  # Cap at 95%
                progress_msg.edit_text(f"Processing: {progress}% complete\nEstimated time remaining: {est_time - elapsed}s")
            else:
                # If we've exceeded the estimated time, just increment a counter
                progress_steps += 1
                progress_msg.edit_text(f"Processing: 95% complete\nAlmost done... (step {progress_steps})")
            
            time.sleep(3)  # Update every 3 seconds
        
        # Check if there was an exception during processing
        if processing_exception[0] is not None:
            progress_msg.edit_text(f"Error during processing: {str(processing_exception[0])}")
            logger.error(f"Error during processing: {processing_exception[0]}")
            log_processing(user_id, "watermark_process", "error", {"error": str(processing_exception[0])})
            return False
        
        # Process completed
        if result[0]:
            progress_msg.edit_text("Processing completed!")
            log_processing(user_id, "watermark_process", "success", {"elapsed_time": int(time.time() - start_time)})
            return True
        else:
            progress_msg.edit_text("Error processing video. Please try again with a different video.")
            log_processing(user_id, "watermark_process", "error", {"error": "Processing function returned False"})
            return False
    except Exception as e:
        progress_msg.edit_text(f"Error during processing: {str(e)}")
        logger.error(f"Error during processing: {e}")
        log_processing(user_id, "watermark_process", "error", {"error": str(e)})
        return False

def store_video_in_channel(update: Update, context: CallbackContext, output_path, caption):
    """Store processed video in the database channel and return message ID"""
    if DATABASE_CHANNEL_ID is None:
        return None
        
    try:
        # Ensure the channel ID is properly formatted
        channel_id = DATABASE_CHANNEL_ID
        # If it's a string and doesn't start with -100, add it (for public channels)
        if isinstance(channel_id, str) and not channel_id.startswith('-100') and not channel_id.startswith('-'):
            channel_id = f"-100{channel_id}"
            
        # Send video to database channel
        with open(output_path, 'rb') as video_file:
            message = context.bot.send_document(
                chat_id=channel_id,
                document=video_file,
                caption=f"User ID: {update.effective_user.id}\n{caption}"
            )
        
        # Return the message ID for future reference
        return message.message_id
    except Exception as e:
        logger.error(f"Error storing video in channel: {e}")
        return None

def button(update: Update, context: CallbackContext) -> None:
    """Handle inline button presses."""
    user_id = str(update.callback_query.from_user.id)
    query = update.callback_query
    query.answer()
    choice = query.data
    
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
        user_prefs = get_user_preferences(user_id)
        if user_prefs is not None and 'watermark_settings' in user_prefs:
            settings = user_prefs['watermark_settings']
            
            # Set up context with saved settings
            context.user_data['wm_type'] = settings['type']
            context.user_data['wm_position'] = settings['position']
            context.user_data['wm_opacity'] = settings['opacity']
            
            if settings['type'] == 'text' and 'text' in settings:
                watermark_text = settings['text']
                video_path = context.user_data['video_path']
                
                # Create output file with unique name in user's temp directory
                user_temp_dir = os.path.dirname(video_path)
                output_filename = f"watermarked_{uuid.uuid4().hex}.mp4"
                output_path = os.path.join(user_temp_dir, output_filename)
                
                # Create progress message and process
                progress_msg = query.message.reply_text('Starting quick watermark process...')
                
                # Process with progress updates
                success = process_with_progress(
                    update, context, 
                    add_text_watermark, 
                    (video_path, watermark_text, settings['position'], settings['opacity'], output_path),
                    progress_msg
                )
                
                if success and os.path.exists(output_path):
                    # Upload watermarked video
                    progress_msg.edit_text('Uploading video...')
                    try:
                        caption = f"Video with saved text watermark"
                        
                        # Try to store in database channel first
                        channel_msg_id = store_video_in_channel(update, context, output_path, caption)
                        
                        # Send to user
                        with open(output_path, 'rb') as video_file:
                            query.message.reply_document(
                                document=video_file,
                                caption=caption
                            )
                        progress_msg.edit_text('Upload complete!')
                        
                        # Log the processed video
                        log_details = {
                            "watermark_type": "text",
                            "position": settings['position'],
                            "opacity": settings['opacity']
                        }
                        if channel_msg_id:
                            log_details["channel_msg_id"] = channel_msg_id
                            
                        log_processing(user_id, "quick_watermark", "success", log_details)
                    except Exception as e:
                        progress_msg.edit_text(f"Error uploading video: {str(e)}")
                        logger.error(f"Error uploading video: {e}")
                        log_processing(user_id, "quick_watermark", "error_upload", {"error": str(e)})
                else:
                    log_processing(user_id, "quick_watermark", "error_processing")
                
                # Clean up
                try:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                    if os.path.exists(video_path):
                        os.remove(video_path)
                except Exception as e:
                    logger.error(f"Error cleaning up files: {e}")
                
                # Reset user data except for preferences
                context.user_data.clear()
            else:
                query.message.reply_text("Image watermarks are not supported in quick mode. Please use regular watermark option.")
                log_processing(user_id, "quick_watermark", "error", {"error": "Unsupported watermark type"})
        else:
            query.message.reply_text("No saved watermark settings found. Please use the regular watermark option first.")
            log_processing(user_id, "quick_watermark", "error", {"error": "No saved settings"})
    
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
        settings = {
            "watermark_settings": {
                'type': context.user_data['wm_type'],
                'position': context.user_data['wm_position'],
                'opacity': context.user_data['wm_opacity']
            }
        }
        save_user_preferences(user_id, settings)
        
        query.message.reply_text('Please enter the text for the watermark:')
        context.user_data['awaiting_input'] = 'watermark_text'
        context.user_data['save_settings'] = True
        
        log_processing(user_id, "save_settings", "success")
    
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
        user_prefs = get_user_preferences(user_id)
        if user_prefs is not None and 'watermark_settings' in user_prefs:
            keyboard.append([InlineKeyboardButton("Quick Watermark (Use Saved Settings)", callback_data="quick_watermark")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.message.reply_text('What would you like to do with the video?', reply_markup=reply_markup)

def handle_text(update: Update, context: CallbackContext) -> None:
    """Handle text messages."""
    user_id = str(update.effective_user.id)
    
    if 'awaiting_input' not in context.user_data:
        update.message.reply_text('Send me a video file first or use /start to begin.')
        return
    
    if context.user_data['awaiting_input'] == 'watermark_text':
        watermark_text = update.message.text
        video_path = context.user_data['video_path']
        position = context.user_data['wm_position']
        opacity = context.user_data['wm_opacity']
        
        # Save text in user preferences if requested
        if context.user_data.get('save_settings', False):
            # First update just the text field in the existing watermark settings
            db.user_preferences.update_one(
                {"user_id": user_id},
                {"$set": {"watermark_settings.text": watermark_text}}
            )
            update.message.reply_text('Your watermark settings have been saved for future use.')
        
        # Create output file with unique name in user's temp directory
        user_temp_dir = os.path.dirname(video_path)
        output_filename = f"watermarked_{uuid.uuid4().hex}.mp4"
        output_path = os.path.join(user_temp_dir, output_filename)
            
        # Create progress message and update it during processing
        progress_msg = update.message.reply_text('Starting watermark process...')
        
        # Process with progress updates
        success = process_with_progress(
            update, context, 
            add_text_watermark, 
            (video_path, watermark_text, position, opacity, output_path),
            progress_msg
        )
        
        if success and os.path.exists(output_path):
            # Upload watermarked video
            progress_msg.edit_text('Uploading video...')
            try:
                caption = f"Video with text watermark at {position}, opacity: {int(opacity*100)}%"
                
                # Try to store in database channel first
                channel_msg_id = store_video_in_channel(update, context, output_path, caption)
                
                # Send to user
                with open(output_path, 'rb') as video_file:
                    update.message.reply_document(
                        document=video_file,
                        caption=caption
                    )
                progress_msg.edit_text('Upload complete!')
                
                # Log the processed video
                log_details = {
                    "watermark_type": "text",
                    "position": position,
                    "opacity": opacity
                }
                if channel_msg_id:
                    log_details["channel_msg_id"] = channel_msg_id
                    
                log_processing(user_id, "watermark", "success", log_details)
            except Exception as e:
                progress_msg.edit_text(f"Error uploading video: {str(e)}")
                logger.error(f"Error uploading video: {e}")
                log_processing(user_id, "watermark", "error_upload", {"error": str(e)})
        
        # Clean up
        try:
            if os.path.exists(output_path):
                os.remove(output_path)
            if os.path.exists(video_path):
                os.remove(video_path)
        except Exception as e:
            logger.error(f"Error cleaning up files: {e}")
        
        # Reset user data
        context.user_data.clear()
        
        # Offer to start over
        update.message.reply_text('Done! Send another video to start again or use /start command.')

def handle_photo(update: Update, context: CallbackContext) -> None:
    """Handle photo uploads for image watermarks."""
    user_id = str(update.effective_user.id)
    
    if 'awaiting_input' not in context.user_data or context.user_data['awaiting_input'] != 'watermark_image':
        update.message.reply_text('Send me a video file first or use /start to begin.')
        return
    
    try:
        # Download the largest version of the photo
        photo_file = update.message.photo[-1].get_file()
        
        # Create a directory for this user if it doesn't exist
        user_temp_dir = os.path.dirname(context.user_data['video_path'])
        
        # Download to user-specific directory with unique filename
        image_filename = f"watermark_{uuid.uuid4().hex}.jpg"
        image_path = os.path.join(user_temp_dir, image_filename)
        photo_file.download(image_path)
        
        video_path = context.user_data['video_path']
        position = context.user_data['wm_position']
        opacity = context.user_data['wm_opacity']
        
        # Create output file with unique name
        output_filename = f"watermarked_{uuid.uuid4().hex}.mp4"
        output_path = os.path.join(user_temp_dir, output_filename)
        
        # Create progress message and update it during processing
        progress_msg = update.message.reply_text('Starting watermark process...')
        
        # Process with progress updates
        success = process_with_progress(
            update, context, 
            add_image_watermark, 
            (video_path, image_path, position, opacity, output_path),
            progress_msg
        )
        
        if success and os.path.exists(output_path):
            # Upload watermarked video
            progress_msg.edit_text('Uploading video...')
            try:
                caption = f"Video with image watermark at {position}, opacity: {int(opacity*100)}%"
                
                # Try to store in database channel first
                channel_msg_id = store_video_in_channel(update, context, output_path, caption)
                
                # Send to user
                with open(output_path, 'rb') as video_file:
                    update.message.reply_document(
                        document=video_file,
                        caption=caption
                    )
                progress_msg.edit_text('Upload complete!')
                
                # Log the processed video
                log_details = {
                    "watermark_type": "image",
                    "position": position,
                    "opacity": opacity
                }
                if channel_msg_id:
                    log_details["channel_msg_id"] = channel_msg_id
                    
                log_processing(user_id, "watermark", "success", log_details)
            except Exception as e:
                progress_msg.edit_text(f"Error uploading video: {str(e)}")
                logger.error(f"Error uploading video: {e}")
                log_processing(user_id, "watermark", "error_upload", {"error": str(e)})
        
        # Clean up
        try:
            if os.path.exists(output_path):
                os.remove(output_path)
            if os.path.exists(image_path):
                os.remove(image_path)
            if os.path.exists(video_path):
                os.remove(video_path)
        except Exception as e:
            logger.error(f"Error cleaning up files: {e}")
        
        # Reset user data
        context.user_data.clear()
        
        # Offer to start over
        update.message.reply_text('Done! Send another video to start again or use /start command.')
    except Exception as e:
        update.message.reply_text(f"Error processing image: {str(e)}")
        logger.error(f"Error in handle_photo: {e}")
        log_processing(user_id, "watermark_image", "error", {"error": str(e)})

# Add command to clear saved preferences
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
            log_processing(user_id, "clear_preferences", "error", {"error": str(e)})
    else:
        update.message.reply_text('Database not available. Your preferences could not be cleared.')
        log_processing(user_id, "clear_preferences", "error", {"error": "Database not available"})

def help_command(update: Update, context: CallbackContext) -> None:
    """Provide help information about using the bot."""
    help_text = """
*Video Watermark Bot Help*

This bot allows you to add watermarks to videos and take screenshots.

*Basic Commands:*
/start - Start the bot
/help - Show this help message
/clear_preferences - Clear your saved watermark settings

*How to use:*
1. Send a video file to the bot (max 50MB)
2. Choose one of the options:
   • Take Screenshot - Generate screenshots from your video
   • Add Watermark - Add text or image watermarks to your video
   • Quick Watermark - Apply your previously saved watermark settings

*Watermark Features:*
• Choose between text or image watermarks
• Select position (upper-left, upper-right, lower-left, lower-right, center)
• Adjust opacity (25%, 50%, 75%, 100%)
• Save your favorite settings for quick access

*Tips:*
• For best results, use videos under 20MB
• Processing large videos may take some time
• You can save your favorite watermark settings for quick use next time
• If processing appears stuck, try again with a smaller video
    """
    update.message.reply_text(help_text, parse_mode='Markdown')
    log_processing(str(update.effective_user.id), "help", "success")

def setup_command(update: Update, context: CallbackContext) -> None:
    """Admin command to set up the database channel."""
    user_id = str(update.effective_user.id)
    
    # Only allow setup from admin user ID (you should define this somewhere)
    # For now, allow any user to run setup for testing
    
    if not context.args or len(context.args) != 1:
        update.message.reply_text('Usage: /setup channel_id')
        return
    
    channel_id = context.args[0]
    
    # Ensure proper format for channel ID
    if not channel_id.startswith('-100') and not channel_id.startswith('-'):
        channel_id = f"-100{channel_id}"
    
    # Try to send a test message to verify bot has access
    try:
        test_msg = context.bot.send_message(
            chat_id=channel_id,
            text=f"Bot setup initiated by user {user_id}. This channel will be used as a database."
        )
        
        # If successful, save the channel ID
        if db is not None:
            db.config.update_one(
                {"key": "database_channel"},
                {"$set": {"value": channel_id}},
                upsert=True
            )
        
        # Set the global variable
        global DATABASE_CHANNEL_ID
        DATABASE_CHANNEL_ID = channel_id
        
        update.message.reply_text(f'Database channel successfully set up! Channel ID: {channel_id}')
        log_processing(user_id, "setup", "success", {"channel_id": channel_id})
    except Exception as e:
        update.message.reply_text(f'Failed to set up channel: {str(e)}\n\nMake sure the bot is an admin in the channel.')
        log_processing(user_id, "setup", "error", {"error": str(e), "channel_id": channel_id})

def status_command(update: Update, context: CallbackContext) -> None:
    """Show status of the bot connections."""
    user_id = str(update.effective_user.id)
    
    status_text = "*Bot Status*\n\n"
    
    # Check MongoDB connection
    mongo_status = "Connected ✅" if db is not None else "Not connected ❌"
    status_text += f"MongoDB: {mongo_status}\n"
    
    # Check database channel
    channel_status = "Set up ✅" if DATABASE_CHANNEL_ID is not None else "Not set up ❌"
    status_text += f"Database Channel: {channel_status}\n"
    
    # Show user preferences
    user_prefs = get_user_preferences(user_id)
    has_prefs = user_prefs is not None and 'watermark_settings' in user_prefs
    prefs_status = "Saved ✅" if has_prefs else "Not saved ❌"
    status_text += f"Your Preferences: {prefs_status}\n"
    
    # Show system info
    status_text += f"\n*System Information*\n"
    status_text += f"FFMPEG: {'Installed ✅' if is_ffmpeg_available() else 'Not installed ❌'}\n"
    status_text += f"Temp directory: {tempfile.gettempdir()}\n"
    
    update.message.reply_text(status_text, parse_mode='Markdown')
    log_processing(user_id, "status", "success")

def is_ffmpeg_available():
    """Check if ffmpeg is available on the system."""
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except:
        return False

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
        dispatcher.add_handler(CommandHandler("status", status_command))
        
        # Admin commands
        dispatcher.add_handler(CommandHandler("setup", setup_command))
        
        # Message handlers
        dispatcher.add_handler(MessageHandler(Filters.video, handle_video))
        dispatcher.add_handler(CallbackQueryHandler(button))
        dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
        dispatcher.add_handler(MessageHandler(Filters.photo, handle_photo))

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
