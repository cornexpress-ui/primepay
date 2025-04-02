from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import PREMIUM_CHANNELS

def main_menu_keyboard():
    """Main menu keyboard with channel options"""
    keyboard = []
    for channel_id, channel_info in PREMIUM_CHANNELS.items():
        keyboard.append([InlineKeyboardButton(
            channel_info["name"], 
            callback_data=f"channel_{channel_id}"
        )])
    
    return InlineKeyboardMarkup(keyboard)

def channel_preview_keyboard(channel_id, current_image_index=0, total_images=1):
    """Keyboard for channel preview with navigation and subscription button"""
    keyboard = []
    
    # Navigation buttons for images (if more than one)
    if total_images > 1:
        nav_buttons = []
        if current_image_index > 0:
            nav_buttons.append(InlineKeyboardButton(
                "◀️ Previous", 
                callback_data=f"prev_{channel_id}_{current_image_index}"
            ))
        if current_image_index < total_images - 1:
            nav_buttons.append(InlineKeyboardButton(
                "Next ▶️", 
                callback_data=f"next_{channel_id}_{current_image_index}"
            ))
        keyboard.append(nav_buttons)
    
    # Subscribe button
    keyboard.append([
        InlineKeyboardButton(
            "🔒 Subscribe", 
            callback_data=f"subscribe_{channel_id}"
        )
    ])
    
    # Back button
    keyboard.append([
        InlineKeyboardButton(
            "🔙 Back to Channels", 
            callback_data="back_to_menu"
        )
    ])
    
    return InlineKeyboardMarkup(keyboard)

def payment_methods_keyboard(channel_id, payment_id):
    """Keyboard with payment options"""
    keyboard = [
        [
            InlineKeyboardButton(
                "💳 UPI ID", 
                callback_data=f"pay_upi_{channel_id}_{payment_id}"
            ),
            InlineKeyboardButton(
                "📱 UPI QR Code", 
                callback_data=f"pay_qr_{channel_id}_{payment_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "📸 Send Payment Screenshot", 
                callback_data=f"screenshot_{payment_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back", 
                callback_data=f"channel_{channel_id}"
            )
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_payment_verification_keyboard(payment_id, user_id, channel_id):
    """Keyboard for admin to approve or reject payment"""
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ Approve", 
                callback_data=f"approve_{payment_id}_{user_id}_{channel_id}"
            ),
            InlineKeyboardButton(
                "❌ Reject", 
                callback_data=f"reject_{payment_id}_{user_id}"
            )
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def renewal_keyboard(subscription_id, channel_id):
    """Keyboard for subscription renewal"""
    keyboard = [
        [
            InlineKeyboardButton(
                "🔄 Renew Subscription", 
                callback_data=f"renew_{subscription_id}_{channel_id}"
            )
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
