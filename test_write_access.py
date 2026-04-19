import asyncio
from pyrogram import Client
from config import settings_manager

async def test():
    app = Client("channelsync_userbot", workdir=".")
    await app.start()
    
    target_channel_id = settings_manager.get("TARGET_CHANNEL_ID")
    print(f"Testing write access to TARGET_CHANNEL_ID: {target_channel_id}")
    
    try:
        await app.send_message(target_channel_id, "Test message from UserBot")
        print("Success! UserBot has write access to the target channel.")
    except Exception as e:
        print(f"Error: {e}")
        
    await app.stop()

if __name__ == "__main__":
    asyncio.run(test())
