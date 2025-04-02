import datetime
import logging
from telegram import Bot
from telegram.error import TelegramError
from telegram.constants import ParseMode
import asyncio

from config import BOT_TOKEN, PREMIUM_CHANNELS, REMINDER_DAYS

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def add_user_to_channel(user_id, channel_id):
    """Add a user to a premium channel"""
    try:
        bot = Bot(BOT_TOKEN)
        
        # Create invite link with limited membership
        invite_link = await bot.create_chat_invite_link(
            chat_id=channel_id,
            member_limit=1,
            name=f"Invite for user {user_id}"
        )
        
        # Send the invite link to the user
        await bot.send_message(
            chat_id=user_id,
            text=f"🎉 Welcome to our premium channel! Click below to join:",
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": "🔓 Join Channel",
                            "url": invite_link.invite_link
                        }
                    ]
                ]
            }
        )
        
        return True
    except Exception as e:
        logger.error(f"Failed to add user {user_id} to channel {channel_id}: {str(e)}")
        return False


async def remove_user_from_channel(user_id, channel_id):
    """Remove a user from a premium channel"""
    try:
        bot = Bot(BOT_TOKEN)
        
        # Ban the user from the channel (this removes them)
        await bot.ban_chat_member(
            chat_id=channel_id,
            user_id=user_id
        )
        
        # Immediately unban to allow them to rejoin in the future
        await bot.unban_chat_member(
            chat_id=channel_id,
            user_id=user_id,
            only_if_banned=True
        )
        
        return True
    except TelegramError as e:
        if "user not found" in str(e).lower():
            # User is not in the channel, consider it a success
            return True
        logger.error(f"Failed to remove user {user_id} from channel {channel_id}: {str(e)}")
        return False


def format_channel_info(channel_id):
    """Format channel information for display"""
    channel = PREMIUM_CHANNELS[channel_id]
    message = f"📚 <b>{channel['name']}</b>\n\n"
    message += f"📝 <b>Description:</b> {channel['description']}\n\n"
    message += f"💰 <b>Price:</b> ₹{channel['price']}\n"
    message += f"⏱ <b>Validity:</b> {channel['validity_days']} days\n\n"
    
    return message


def calculate_expiry_date(days):
    """Calculate expiry date from now"""
    return datetime.datetime.utcnow() + datetime.timedelta(days=days)


def get_channel_name_by_id(channel_id):
    """Get channel name from its ID"""
    for key, channel in PREMIUM_CHANNELS.items():
        if channel["channel_id"] == channel_id:
            return channel["name"]
    return "Unknown Channel"


def format_datetime(dt):
    """Format datetime object to readable string"""
    return dt.strftime("%d %b %Y")


async def process_expired_subscriptions(bot, db):
    """Process expired subscriptions and remove users from channels"""
    expired = db.get_expired_subscriptions()
    for subscription in expired:
        # Remove user from channel
        success = await remove_user_from_channel(
            subscription["user_id"],
            subscription["channel_id"]
        )
        
        if success:
            # Update subscription status
            db.update_subscription(
                subscription["_id"],
                {"status": "expired"}
            )
            
            # Notify user
            channel_name = get_channel_name_by_id(subscription["channel_id"])
            try:
                await bot.send_message(
                    chat_id=subscription["user_id"],
                    text=f"ℹ️ Your subscription to <b>{channel_name}</b> has expired. "
                         f"To regain access, please renew your subscription.",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Failed to notify user {subscription['user_id']} about expiry: {str(e)}")


async def send_renewal_reminders(bot, db):
    """Send renewal reminders to users whose subscriptions are about to expire"""
    expiring = db.get_expiring_subscriptions(REMINDER_DAYS)
    for subscription in expiring:
        channel_name = get_channel_name_by_id(subscription["channel_id"])
        expiry_date = format_datetime(subscription["expires_at"])
        
        # Find the channel config
        channel_key = None
        for key, channel in PREMIUM_CHANNELS.items():
            if channel["channel_id"] == subscription["channel_id"]:
                channel_key = key
                break
        
        if not channel_key:
            continue
            
        try:
            from keyboards import renewal_keyboard
            keyboard = renewal_keyboard(str(subscription["_id"]), channel_key)
            
            await bot.send_message(
                chat_id=subscription["user_id"],
                text=f"⚠️ <b>Subscription Renewal Reminder</b>\n\n"
                     f"Your subscription to <b>{channel_name}</b> will expire on <b>{expiry_date}</b> "
                     f"({REMINDER_DAYS} days from now).\n\n"
                     f"To maintain uninterrupted access, please renew your subscription.",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Failed to send renewal reminder to user {subscription['user_id']}: {str(e)}")
