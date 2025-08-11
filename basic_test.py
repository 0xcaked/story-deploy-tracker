import asyncio
from telegram import Bot

async def main():
    print("Starting basic test...")
    
    try:
        print("Importing telegram...")
        print("Telegram imported successfully!")
        
        print("Creating bot...")
        bot = Bot("8450398408:AAFcKVmcNRDuvqTpbeigR-p3L8XDvZuEx6s")
        print("Bot created!")
        
        print("Sending message...")
        result = await bot.send_message(chat_id="-1002714144239", text="Test message")
        print(f"Message sent! ID: {result.message_id}")
        
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        raise

    print("Test completed!")

if __name__ == "__main__":
    asyncio.run(main())
