import logging
import sys
import time
from telegram import Bot

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('monitor.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_BOT_TOKEN = "8450398408:AAFcKVmcNRDuvqTpbeigR-p3L8XDvZuEx6s"
CHAT_ID = "-1002714144239"

def main():
    logger.info("Starting monitor...")
    
    # Initialize bot
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    try:
        # Send startup message
        logger.info("Sending test message...")
        bot.send_message(
            chat_id=CHAT_ID,
            text="🔄 Monitor starting..."
        )
        logger.info("Test message sent!")
        
        # Keep the script running
        while True:
            time.sleep(5)
            
    except KeyboardInterrupt:
        logger.info("Stopping monitor...")
        bot.send_message(
            chat_id=CHAT_ID,
            text="⏹ Monitor stopping..."
        )
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        try:
            bot.send_message(
                chat_id=CHAT_ID,
                text=f"❌ Error: {str(e)}"
            )
        except:
            pass

if __name__ == "__main__":
    main()
