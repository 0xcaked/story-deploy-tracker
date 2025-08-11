import os
import sys
import logging
from telegram import Bot

# Set up detailed logging
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG for more detailed logs
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

# Get the root logger
logger = logging.getLogger()

def test_telegram():
    try:
        # Print Python version and environment info
        logger.info(f"Python Version: {sys.version}")
        logger.info(f"Current Directory: {os.getcwd()}")
        
        # Initialize bot
        logger.info("Creating bot instance...")
        bot = Bot("8450398408:AAFcKVmcNRDuvqTpbeigR-p3L8XDvZuEx6s")
        
        # Test connection
        logger.info("Testing bot connection...")
        bot_info = bot.get_me()
        logger.info(f"Connected as: {bot_info.username}")
        
        # Send test message
        logger.info("Sending test message...")
        message = bot.send_message(
            chat_id="-1002714144239",
            text="🟢 Telegram Bot Test Message"
        )
        logger.info(f"Message sent! Message ID: {message.message_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error occurred: {str(e)}", exc_info=True)
        return False

if __name__ == "__main__":
    logger.info("Starting bot test...")
    success = test_telegram()
    if success:
        logger.info("Test completed successfully!")
    else:
        logger.error("Test failed!")
