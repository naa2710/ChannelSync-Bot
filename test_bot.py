import os
import asyncio
from pyrogram import Client
from dotenv import load_dotenv

load_dotenv()

app = Client('channelsync_userbot', api_id=int(os.getenv('TELEGRAM_API_ID')), api_hash=os.getenv('TELEGRAM_API_HASH'), workdir='.')

async def main():
    async with app:
        await app.send_message('me', '✅ UserBot is connected and can send messages! If you see this, the session works.')
        print('STATUS: TEST_MSG_SENT')

asyncio.run(main())
