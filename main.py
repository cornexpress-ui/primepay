import asyncio
import logging
import os
import datetime
from telegram.ext import ApplicationBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import signal

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

async def scheduled_tasks(application):
    """Run scheduled tasks"""
    try:
        # Process expired subscriptions
        await process_expired_subscriptions(application.bot, db)
        
        # Send renewal reminders
        await send_renewal_reminders(application.bot, db)
    except Exception as e:
        logger.error(f"Error in scheduled tasks: {str(e)}")


# Define stop signals handler
def stop_signals_handler():
    """Handle stop signals"""
    loop = asyncio.get_event_loop()
    loop.stop()
    logger.info("Bot stopped!")


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
        args=[application]
    )
    
    # Start the scheduler
    scheduler.start()
    
    # Start the bot
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Keep the application running
    stop_event = asyncio.Event()
    
    # Set signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM, signal.SIGABRT):
        loop.add_signal_handler(s, lambda: stop_event.set())
    
    logger.info("Bot started!")
    
    # Wait until a stop signal is received
    await stop_event.wait()
    
    # Clean up
    logger.info("Stopping the bot...")
    await application.stop()
    await application.shutdown()
    scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
