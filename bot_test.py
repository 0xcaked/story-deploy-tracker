import os
import asyncio
import logging
from telegram import Bot
from telegram.constants import ParseMode

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    # Get token from environment variable
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("ALERT_CHAT_ID")
    
    if not token:
        logger.error("No token provided")
        return
        
    try:
        # Create bot instance
        bot = Bot(token=token)
        
        # Send a test message
        logger.info("Sending test message...")
        await bot.send_message(chat_id=chat_id, text="🚀 Bot test message")
        logger.info("Test message sent successfully")
        
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
