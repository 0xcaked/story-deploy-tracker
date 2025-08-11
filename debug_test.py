import requests
import logging
import sys
from datetime import datetime

# Set up logging to both file and console
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_test.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def main():
    try:
        # Log basic system info
        logger.info("Python version: %s", sys.version)
        logger.info("Current time: %s", datetime.now())
        
        token = "8450398408:AAFcKVmcNRDuvqTpbeigR-p3L8XDvZuEx6s"
        chat_id = "-1002714144239"
        
        logger.info("Testing Telegram API connection...")
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        
        # Try to send a message
        response = requests.post(url, json={
            "chat_id": chat_id,
            "text": "🔄 Test message with logging"
        }, timeout=30)
        
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response body: {response.text}")
        
        with open('bot_response.txt', 'w') as f:
            f.write(f"Status: {response.status_code}\n")
            f.write(f"Response: {response.text}\n")
        
    except Exception as e:
        logger.error("Error occurred:", exc_info=True)
        with open('bot_error.txt', 'w') as f:
            f.write(f"Error: {str(e)}\n")

if __name__ == "__main__":
    logger.info("Starting API test with logging...")
    main()
    logger.info("Test completed.")
