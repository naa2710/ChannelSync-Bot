import asyncio
from pyrogram import Client
from core.transfer import transfer_last_n_files
from config import settings_manager
import logging

logging.basicConfig(level=logging.INFO)

async def test():
    app = Client("channelsync_userbot", workdir=".")
    await app.start()
    print("UserBot started.")
    
    target = "designcv1"
    try:
        chat = await app.get_chat(target)
        print(f"Chat resolved: {chat.title}")
        
        print("Checking messages...")
        count = 0
        from core.transfer import is_valid_message_type, message_has_required_hashtag
        async for msg in app.get_chat_history(chat.id, limit=10):
            print(f"MSG {msg.id}: has_photo={bool(msg.photo)}, has_doc={bool(msg.document)}, text_len={len(msg.text or '')}")
            valid_type = is_valid_message_type(msg)
            valid_hash = message_has_required_hashtag(msg.text, msg.caption)
            print(f"  Valid Type: {valid_type}, Valid Hash: {valid_hash}")
            if valid_type and valid_hash:
                count += 1
        print(f"Found {count} valid messages to transfer.")
        
        # Test transfer (will do actual transfer to TARGET_CHANNEL_ID)
        await transfer_last_n_files(app, chat.id, limit=2)
        
    except Exception as e:
        print(f"Error: {e}")
        
    await app.stop()

if __name__ == "__main__":
    asyncio.run(test())
