import asyncio
from pyrogram import Client
from config import API_ID, API_HASH, settings_manager
from core.sources import add_source
from core.logger import get_logger

logger = get_logger("MIGRATION")

async def migrate():
    app = Client("channelsync_userbot", api_id=API_ID, api_hash=API_HASH, workdir=".")
    await app.start()
    
    source_ids = settings_manager.get("ALLOWED_SOURCE_CHAT_IDS") or []
    logger.info(f"جاري جلب أسماء {len(source_ids)} مصدر...")
    
    count = 0
    for chat_id in source_ids:
        try:
            chat = await app.get_chat(chat_id)
            add_source(chat_id, title=chat.title)
            count += 1
            if count % 10 == 0:
                logger.info(f"تمت معالجة {count} مصادر...")
            await asyncio.sleep(0.5) # تجنب الحظر أثناء المزامنة
        except Exception as e:
            logger.error(f"فشل جلب اسم {chat_id}: {e}")
            
    logger.info(f"اكتملت المزامنة. تم تحديث أسماء {count} مصادر.")
    await app.stop()

if __name__ == "__main__":
    asyncio.run(migrate())
