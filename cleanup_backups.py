import asyncio
from pyrogram import Client
from config import API_ID, API_HASH, PHONE, STRING_SESSION, get_data_path

app = Client(
    "channelsync_userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    phone_number=PHONE,
    session_string=STRING_SESSION,
    workdir="."
)

async def cleanup_and_upload():
    await app.start()
    print("متصل باليوزر بوت...")
    
    deleted_count = 0
    # البحث في الرسائل المحفوظة (me)
    async for message in app.get_chat_history("me", limit=300):
        if message.document and message.caption and "Backup:" in message.caption:
            await message.delete()
            deleted_count += 1
            print(f"تم حذف نسخة احتياطية قديمة: {message.caption.replace(chr(10), ' ')}")
            
    print(f"تم مسح {deleted_count} نسخ احتياطية قديمة بالكامل من الحساب!")
    
    # الرفع الفوري للنسخة الحالية الصحيحة
    from datetime import datetime
    import os
    for filename in ["settings.json", "index.db"]:
        path = get_data_path(filename)
        if os.path.exists(path):
            await app.send_document(
                "me",
                path,
                caption=f"📦 Backup: {filename}\n🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (FRESH UPLOAD)",
                file_name=f"backup_{filename}"
            )
            print(f"✅ تم رفع النسخة الجديدة الصالحة من: {filename}")
    
    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(cleanup_and_upload())
