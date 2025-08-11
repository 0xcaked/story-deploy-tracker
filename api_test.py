import requests
import logging

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    try:
        token = "8450398408:AAFcKVmcNRDuvqTpbeigR-p3L8XDvZuEx6s"
        chat_id = "-1002714144239"
        
        logger.info("Testing Telegram API connection...")
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        
        response = requests.post(url, json={
            "chat_id": chat_id,
            "text": "🔄 Test message using requests"
        })
        
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response body: {response.text}")
        
        response.raise_for_status()
        logger.info("Message sent successfully!")
        
    except Exception as e:
        logger.error(f"Error occurred: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    logger.info("Starting API test...")
    main()
