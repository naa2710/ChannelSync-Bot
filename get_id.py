import asyncio
from pyrogram import Client

async def test():
    app = Client("channelsync_userbot", workdir=".")
    await app.start()
    chat = await app.get_chat("designcv1")
    print(chat.id)
    await app.stop()

if __name__ == "__main__":
    asyncio.run(test())
