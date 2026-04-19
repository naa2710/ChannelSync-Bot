import asyncio
from pyrogram import Client
from pyrogram.enums import ChatType
from config import API_ID, API_HASH, settings_manager
from core.sources import add_source, get_sources
from core.transfer import transfer_last_n_files
from core.logger import get_logger

logger = get_logger("SYNC")

async def sync_and_fetch():
    app = Client("channelsync_userbot", api_id=API_ID, api_hash=API_HASH, workdir=".")
    await app.start()
    logger.info("جاري فحص جميع المجموعات والقنوات التي يشترك فيها الحساب...")
    
    target_channel_id = settings_manager.get("TARGET_CHANNEL_ID")
    count = 0
    
    async for dialog in app.get_dialogs():
        chat = dialog.chat
        if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
            if chat.id == target_channel_id:
                continue
                
            if add_source(chat.id):
                logger.info(f"✅ تمت إضافة مصدر قديم جديد: {chat.title} ({chat.id})")
                count += 1
    
    logger.info(f"اكتملت المزامنة. تمت إضافة {count} مصادر جديدة.")
    
    # تفريغ أمر الجلب الجماعي لجميع المصادر الحالية بعد المزامنة
    settings_manager.set("TRIGGER_FETCH_ALL", True)
    logger.info("تم إصدار أمر لـ UserBot ببدء سحب الملفات بأثر رجعي لجميع المصادر.")
    
    await app.stop()

if __name__ == "__main__":
    asyncio.run(sync_and_fetch())
