import os
import datetime
from telegram import Update, InputMediaPhoto
# Fixed imports for PTB v20+
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackContext, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ConversationHandler, filters
)

import logging
from bson.objectid import ObjectId

from config import PREMIUM_CHANNELS, PAYMENT_METHODS, ADMIN_ID
from keyboards import (
    main_menu_keyboard, channel_preview_keyboard, 
    payment_methods_keyboard, admin_payment_verification_keyboard
)
from database import (
    get_user, update_user, create_payment, update_payment, 
    create_subscription, update_subscription
)
from utils import (
    add_user_to_channel, format_channel_info, 
    calculate_expiry_date
)

# States for conversation handler
AWAITING_SCREENSHOT = 1

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start_command(update: Update, context: CallbackContext) -> None:
    """Handle /start command"""
    user = update.effective_user
    
    # Log user details
    get_user(user.id)
    update_user(user.id, {
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "last_seen": datetime.datetime.utcnow()
    })
    
    # Send welcome message
    await update.message.reply_photo(
        photo="https://envs.sh/jYU.jpg",  # Replace with your welcome image
        caption=(
            f"👋 Welcome, {user.first_name}!\n\n"
            "🌟 <b>Premium Study Materials Bot</b> 🌟\n\n"
            "Access exclusive premium study materials to accelerate your learning journey.\n\n"
            "Select a channel below to view details and subscribe:"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard()
    )


async def help_command(update: Update, context: CallbackContext) -> None:
    """Handle /help command"""
    await update.message.reply_text(
        "📚 <b>Premium Study Materials - Help</b>\n\n"
        "Here's how to use this bot:\n\n"
        "1️⃣ Choose a premium channel from the main menu\n"
        "2️⃣ Browse through preview images to see what's included\n"
        "3️⃣ Subscribe by selecting the payment option\n"
        "4️⃣ Complete the payment and submit a screenshot\n"
        "5️⃣ Wait for admin approval to gain access\n\n"
        "📝 <b>Commands:</b>\n"
        "/start - Start the bot and see the main menu\n"
        "/help - Show this help message\n"
        "/subscriptions - View your active subscriptions\n\n"
        "For assistance, contact our support team.",
        parse_mode=ParseMode.HTML
    )


async def subscriptions_command(update: Update, context: CallbackContext) -> None:
    """Handle /subscriptions command"""
    from database import get_user_subscriptions
    
    user_id = update.effective_user.id
    subscriptions = get_user_subscriptions(user_id)
    
    if not subscriptions:
        await update.message.reply_text(
            "You don't have any active subscriptions.\n\n"
            "Use /start to browse our premium channels and subscribe."
        )
        return
    
    active_subs = [sub for sub in subscriptions if sub["status"] == "active"]
    
    if not active_subs:
        await update.message.reply_text(
            "You don't have any active subscriptions.\n\n"
            "Use /start to browse our premium channels and subscribe."
        )
        return
    
    text = "📚 <b>Your Active Subscriptions</b>\n\n"
    
    for sub in active_subs:
        channel_id = sub["channel_id"]
        channel_name = None
        
        # Find the channel name
        for key, channel in PREMIUM_CHANNELS.items():
            if channel["channel_id"] == channel_id:
                channel_name = channel["name"]
                break
        
        if not channel_name:
            channel_name = "Unknown Channel"
        
        expiry_date = sub["expires_at"].strftime("%d %b %Y")
        text += f"📌 <b>{channel_name}</b>\n"
        text += f"   Expires on: {expiry_date}\n\n"
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML
    )


async def button_callback(update: Update, context: CallbackContext) -> None:
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    
    # Back to main menu
    if data == "back_to_menu":
        await query.edit_message_caption(
            caption="Select a premium channel to view details and subscribe:",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Channel selection
    if data.startswith("channel_"):
        channel_id = data.split("_")[1]
        channel = PREMIUM_CHANNELS[channel_id]
        
        if not channel["preview_images"]:
            await query.edit_message_caption(
                caption=format_channel_info(channel_id),
                parse_mode=ParseMode.HTML,
                reply_markup=channel_preview_keyboard(channel_id, 0, 0)
            )
            return
        
        # Show first preview image
        await query.message.reply_photo(
            photo=channel["preview_images"][0],
            caption=format_channel_info(channel_id),
            parse_mode=ParseMode.HTML,
            reply_markup=channel_preview_keyboard(
                channel_id, 
                0, 
                len(channel["preview_images"])
            )
        )
        return
    
    # Image navigation
    if data.startswith("next_") or data.startswith("prev_"):
        _, channel_id, current_index = data.split("_")
        current_index = int(current_index)
        
        if data.startswith("next_"):
            new_index = current_index + 1
        else:
            new_index = current_index - 1
        
        channel = PREMIUM_CHANNELS[channel_id]
        total_images = len(channel["preview_images"])
        
        if 0 <= new_index < total_images:
            await query.message.edit_media(
                media=InputMediaPhoto(
                    media=channel["preview_images"][new_index],
                    caption=format_channel_info(channel_id),
                    parse_mode=ParseMode.HTML
                ),
                reply_markup=channel_preview_keyboard(
                    channel_id, 
                    new_index, 
                    total_images
                )
            )
        return
    
    # Subscribe to channel
    if data.startswith("subscribe_"):
        channel_id = data.split("_")[1]
        channel = PREMIUM_CHANNELS[channel_id]
        
        # Create a payment record
        payment_id = create_payment(
            user_id=user_id,
            channel_id=channel["channel_id"],
            amount=channel["price"],
            payment_method=None
        )
        
        await query.edit_message_caption(
            caption=(
                f"💳 <b>Payment for {channel['name']}</b>\n\n"
                f"Amount: ₹{channel['price']}\n"
                f"Validity: {channel['validity_days']} days\n\n"
                "Please select your payment method:"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=payment_methods_keyboard(channel_id, payment_id)
        )
        return
    
    # Payment method selection
    if data.startswith("pay_"):
        _, method, channel_id, payment_id = data.split("_")
        channel = PREMIUM_CHANNELS[channel_id]
        
        # Update payment method
        update_payment(ObjectId(payment_id), {"payment_method": method})
        
        if method == "upi":
            await query.edit_message_caption(
                caption=(
                    f"💳 <b>Pay via UPI ID</b>\n\n"
                    f"Amount: ₹{channel['price']}\n\n"
                    f"UPI ID: <code>{PAYMENT_METHODS['upi_id']}</code>\n\n"
                    "After completing the payment, please send a screenshot for verification."
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=payment_methods_keyboard(channel_id, payment_id)
            )
        elif method == "qr":
            await query.message.reply_photo(
                photo=PAYMENT_METHODS["qr_code_url"],
                caption=(
                    f"💳 <b>Pay via UPI QR Code</b>\n\n"
                    f"Amount: ₹{channel['price']}\n\n"
                    "Scan the QR code above to pay.\n\n"
                    "After completing the payment, please send a screenshot for verification."
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=payment_methods_keyboard(channel_id, payment_id)
            )
        return
    
    # Send payment screenshot
    if data.startswith("screenshot_"):
        payment_id = data.split("_")[1]
        context.user_data["current_payment"] = payment_id
        
        await query.edit_message_caption(
            caption=(
                "📸 <b>Send Payment Screenshot</b>\n\n"
                "Please send a screenshot of your payment as proof.\n\n"
                "Make sure the screenshot clearly shows:\n"
                "• Transaction ID\n"
                "• Payment amount\n"
                "• Date and time\n\n"
                "Send the image now. Send /cancel to cancel."
            ),
            parse_mode=ParseMode.HTML
        )
        return AWAITING_SCREENSHOT
    
    # Process payment approval (Admin only)
    if data.startswith("approve_") and user_id == ADMIN_ID:
        _, payment_id, user_id, channel_id = data.split("_")
        user_id = int(user_id)
        
        # Get channel details
        channel = None
        for key, ch in PREMIUM_CHANNELS.items():
            if ch["channel_id"] == channel_id:
                channel = ch
                break
        
        if not channel:
            await query.edit_message_text(
                text="Error: Channel not found.",
                reply_markup=None
            )
            return
        
        # Calculate expiry date
        expires_at = calculate_expiry_date(channel["validity_days"])
        
        # Create subscription
        subscription_id = create_subscription(
            user_id=user_id,
            channel_id=channel_id,
            expires_at=expires_at
        )
        
        # Update payment status
        update_payment(
            ObjectId(payment_id),
            {"status": "approved"}
        )
        
        # Add user to channel
        success = await add_user_to_channel(user_id, channel_id)
        
        if success:
            # Notify admin
            await query.edit_message_text(
                text=f"✅ Payment approved and user added to channel {channel['name']}.",
                reply_markup=None
            )
            
            # Notify user
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"🎉 <b>Congratulations!</b>\n\n"
                    f"Your payment for <b>{channel['name']}</b> has been approved.\n"
                    f"You've been added to the channel.\n\n"
                    f"Your subscription will expire on {expires_at.strftime('%d %b %Y')}.\n\n"
                    f"Enjoy your premium content!"
                ),
                parse_mode=ParseMode.HTML
            )
        else:
            await query.edit_message_text(
                text=f"⚠️ Payment approved but failed to add user to channel. Please add manually.",
                reply_markup=None
            )
        return
    
    # Process payment rejection (Admin only)
    if data.startswith("reject_") and user_id == ADMIN_ID:
        _, payment_id, user_id = data.split("_")
        user_id = int(user_id)
        
        # Update payment status
        update_payment(
            ObjectId(payment_id),
            {"status": "rejected"}
        )
        
        # Notify admin
        await query.edit_message_text(
            text="❌ Payment rejected.",
            reply_markup=None
        )
        
        # Notify user
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "❌ <b>Payment Rejected</b>\n\n"
                "Your payment could not be verified.\n\n"
                "Please try again or contact support for assistance."
            ),
            parse_mode=ParseMode.HTML
        )
        return
    
    # Subscription renewal
    if data.startswith("renew_"):
        _, subscription_id, channel_id = data.split("_")
        channel = PREMIUM_CHANNELS[channel_id]
        
        # Create a new payment record
        payment_id = create_payment(
            user_id=user_id,
            channel_id=channel["channel_id"],
            amount=channel["price"],
            payment_method=None
        )
        
        await query.edit_message_text(
            text=(
                f"💳 <b>Renewal Payment for {channel['name']}</b>\n\n"
                f"Amount: ₹{channel['price']}\n"
                f"Validity: {channel['validity_days']} days\n\n"
                "Please select your payment method:"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=payment_methods_keyboard(channel_id, payment_id)
        )
        return


async def screenshot_handler(update: Update, context: CallbackContext) -> int:
    """Handle payment screenshot submission"""
    if not context.user_data.get("current_payment"):
        await update.message.reply_text(
            "❌ Error: No active payment process found.\n\n"
            "Please use /start to begin a new subscription."
        )
        return ConversationHandler.END
    
    payment_id = context.user_data["current_payment"]
    user_id = update.effective_user.id
    
    # Check if the message contains a photo
    if not update.message.photo:
        await update.message.reply_text(
            "Please send an image as the payment screenshot."
        )
        return AWAITING_SCREENSHOT
    
    # Get the highest resolution photo
    photo = update.message.photo[-1]
    file_id = photo.file_id
    
    # Update the payment record with the screenshot
    update_payment(
        ObjectId(payment_id),
        {"screenshot_file_id": file_id}
    )
    
    # Get payment details from database
    from database import payments
    payment = payments.find_one({"_id": ObjectId(payment_id)})
    
    if not payment:
        await update.message.reply_text(
            "❌ Error: Payment record not found.\n\n"
            "Please contact support."
        )
        return ConversationHandler.END
    
    # Get channel details
    channel_id = payment["channel_id"]
    channel_name = None
    
    for key, channel in PREMIUM_CHANNELS.items():
        if channel["channel_id"] == channel_id:
            channel_name = channel["name"]
            break
    
    if not channel_name:
        channel_name = "Unknown Channel"
    
    # Notify user
    await update.message.reply_text(
        "✅ <b>Payment Screenshot Received</b>\n\n"
        "Your payment is being verified. This may take some time.\n"
        "You'll receive a notification once your payment is approved.",
        parse_mode=ParseMode.HTML
    )
    
    # Forward to admin for verification
    admin_message = await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=file_id,
        caption=(
            f"💰 <b>New Payment Verification</b>\n\n"
            f"User ID: <code>{user_id}</code>\n"
            f"Channel: {channel_name}\n"
            f"Amount: ₹{payment['amount']}\n"
            f"Payment Method: {payment['payment_method']}\n\n"
            f"Please verify and approve/reject this payment."
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=admin_payment_verification_keyboard(
            payment_id, 
            user_id, 
            channel_id
        )
    )
    
    # Clear conversation state
    context.user_data.pop("current_payment", None)
    return ConversationHandler.END


async def cancel_handler(update: Update, context: CallbackContext) -> int:
    """Cancel the current operation"""
    context.user_data.pop("current_payment", None)
    
    await update.message.reply_text(
        "❌ Operation cancelled.\n\nUse /start to return to the main menu."
    )
    return ConversationHandler.END


def register_handlers(app):
    """Register all handlers"""
    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("subscriptions", subscriptions_command))
    
    # Button callback handler
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # Conversation handler for screenshots
    screenshot_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback, pattern=r'^screenshot_')],
        states={
            AWAITING_SCREENSHOT: [
                MessageHandler(filters.PHOTO, screenshot_handler),
                CommandHandler("cancel", cancel_handler)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)],
    )
    
    app.add_handler(screenshot_conv)
