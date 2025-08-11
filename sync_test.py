import logging
from telegram import Bot
import time

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    try:
        logger.info("Creating bot instance...")
        bot = Bot("8450398408:AAFcKVmcNRDuvqTpbeigR-p3L8XDvZuEx6s")
        
        logger.info("Sending test message...")
        bot.send_message(
            chat_id="-1002714144239",
            text="🔄 Bot test message (sync)"
        )
        logger.info("Message sent successfully!")
        
    except Exception as e:
        logger.error(f"Error occurred: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    logger.info("Starting bot test...")
    main()
