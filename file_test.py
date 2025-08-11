import sys
import traceback

with open('test_output.txt', 'w') as f:
    f.write("Starting basic test...\n")

    try:
        f.write("Importing telegram...\n")
        from telegram import Bot
        f.write("Telegram imported successfully!\n")
        
        f.write("Creating bot...\n")
        bot = Bot("8450398408:AAFcKVmcNRDuvqTpbeigR-p3L8XDvZuEx6s")
        f.write("Bot created!\n")
        
        f.write("Sending message...\n")
        result = bot.send_message(chat_id="-1002714144239", text="Test message")
        f.write(f"Message sent! ID: {result.message_id}\n")
        
    except Exception as e:
        f.write(f"Error occurred: {str(e)}\n")
        f.write("Full traceback:\n")
        traceback.print_exc(file=f)
        raise

    f.write("Test completed!\n")
    f.flush()
