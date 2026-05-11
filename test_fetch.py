import asyncio
import sys
from pyrogram import Client
from config import API_ID, API_HASH, PHONE, STRING_SESSION, settings_manager

app = Client(
    "channelsync_userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    phone_number=PHONE,
    session_string=STRING_SESSION,
    workdir="."
)

async def test_fetch():
    await app.start()
    from core.transfer import transfer_last_n_files
    
    # 获取目标渠道
    target_channel = getattr(settings_manager, "get")("TARGET_CHANNEL_ID")
    print(f"Target Channel: {target_channel}")
    
    sources = getattr(settings_manager, "get")("ALLOWED_SOURCE_CHAT_IDS")
    print(f"Sources: {sources}")
    
    if not sources:
        print("لا توجد مصادر لفحصها!")
        await app.stop()
        return

    # سنجرب نقل ملف واحد من أول مصدر
    print(f"تجربة سحب ملف واحد من المصدر الأول: {sources[0]}")
    try:
        await transfer_last_n_files(app, sources[0], limit=1)
        print("✅ أمر السحب تم تنفيذه دون أخطاء.")
    except Exception as e:
        print(f"❌ خطأ أثناء السحب: {e}")

    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_fetch())
