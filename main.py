import asyncio
import logging
import os
import datetime
from telegram.ext import ApplicationBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

from config import BOT_TOKEN
from handlers import register_handlers
import database as db
from utils import process_expired_subscriptions, send_renewal_reminders

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def scheduled_tasks(bot):
    """Run scheduled tasks"""
    try:
        # Process expired subscriptions
        await process_expired_subscriptions(bot, db)
        
        # Send renewal reminders
        await send_renewal_reminders(bot, db)
    except Exception as e:
        logger.error(f"Error in scheduled tasks: {str(e)}")


async def main():
    """Start the bot"""
    # Initialize the application
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Register handlers
    register_handlers(application)
    
    # Initialize scheduler
    scheduler = AsyncIOScheduler(timezone=pytz.UTC)
    
    # Schedule tasks to run daily at midnight UTC
    scheduler.add_job(
        scheduled_tasks,
        'cron',
        hour=0,
        minute=0,
        args=[application.bot]
    )
    
    # Start the scheduler
    scheduler.start()
    
    # Start the bot
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Run the bot until a signal is received
    await application.idle()


if __name__ == "__main__":
    asyncio.run(main())
